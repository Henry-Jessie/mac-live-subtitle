"""
Deepgram streaming transcription implementation for ultra-low latency.
Uses WebSocket for real-time audio streaming and transcription.
"""
import asyncio
import logging
import json
from typing import Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
    Microphone,
)
import openai

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Transcription result data."""
    detected_language: str
    original_text: str
    chinese_translation: str
    timestamp: str
    is_final: bool = True  # Whether this is a final or interim result


class DeepgramTranscriber:
    """Handles real-time transcription using Deepgram WebSocket API."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "nova-2",  # nova-2 is optimized for real-time
        language: str = "en",
        polish_model: str = "gpt-4o-mini",
        polish_api_key: str = None,
        polish_base_url: str = None,
        interim_results: bool = True,  # Show partial results for lower latency
    ):
        self.api_key = api_key
        self.model_name = model
        self.language = language
        self.interim_results = interim_results
        
        # Polish model configuration
        self.polish_model = polish_model
        self.context_window = 40  # Keep last 40 transcriptions for context
        
        # Configure Deepgram client
        config = DeepgramClientOptions(
            options={"keepalive": "true"}  # Keep connection alive
        )
        self.deepgram = DeepgramClient(api_key, config)
        
        # Configure polish client (OpenAI/OpenRouter)
        if polish_base_url or polish_api_key:
            self.polish_client = openai.Client(
                api_key=polish_api_key or api_key,
                base_url=polish_base_url
            )
        else:
            # Assume OpenAI if no special config
            self.polish_client = openai.Client(api_key=polish_api_key or api_key)
        
        # Connection state
        self.connection = None
        self.is_running = False
        self.connection_ready = False
        self.main_loop = None  # Store main event loop
        
        # Reconnection settings
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 2.0  # seconds
        self.is_reconnecting = False
        
        # Callbacks
        self._transcription_callback: Optional[Callable[[TranscriptionResult], None]] = None
        self._error_callback: Optional[Callable[[str], None]] = None
        
        # Context management
        self.recent_transcriptions: List[TranscriptionResult] = []
        self.pending_text = ""  # Accumulate interim results
        self.last_translation_time = 0  # Track last translation time
        self.translation_threshold = 1.0  # Translate every 1 second
        
        # Polish task for async processing
        self.polish_queue = asyncio.Queue()
        self.polish_task = None
        
        logger.info(f"Initialized Deepgram transcriber with model: {self.model_name}")
        logger.info(f"Interim results: {self.interim_results}, Polish model: {self.polish_model}")
    
    def set_transcription_callback(self, callback: Callable[[TranscriptionResult], None]):
        """Set callback for transcription results."""
        self._transcription_callback = callback
    
    def set_error_callback(self, callback: Callable[[str], None]):
        """Set callback for errors."""
        self._error_callback = callback
    
    async def start(self):
        """Start the transcription service."""
        self.is_running = True
        self.main_loop = asyncio.get_running_loop()  # Save main event loop
        
        try:
            # Create WebSocket connection
            self.connection = self.deepgram.listen.live.v("1")
            
            # Configure event handlers
            self.connection.on(LiveTranscriptionEvents.Open, self._on_open)
            self.connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
            self.connection.on(LiveTranscriptionEvents.Metadata, self._on_metadata)
            self.connection.on(LiveTranscriptionEvents.Error, self._on_error)
            self.connection.on(LiveTranscriptionEvents.Close, self._on_close)
            self.connection.on(LiveTranscriptionEvents.UtteranceEnd, self._on_utterance_end)
            
            # Configure live transcription options
            logger.info(f"Configuring Deepgram with model: {self.model_name}, language: {self.language}")
            options = LiveOptions(
                model=self.model_name,
                language=self.language,  # Multi-language mode
                punctuate=True,
                smart_format=True,
                interim_results=self.interim_results,
                utterance_end_ms=1000,  # End of speech detection
                vad_events=True,  # Voice activity detection
                endpointing=300,  # Silence duration before finalizing
                encoding="linear16",
                sample_rate=16000,
                channels=1,
            )
            
            # Start connection
            # logger.debug(f"Starting connection with options: model={self.model_name}, language={self.language}")
            if self.connection.start(options):
                logger.info("Deepgram WebSocket connection established")
                
                # Start polish processor
                self.polish_task = asyncio.create_task(self._polish_processor())
                # logger.debug("Polish processor task started")
            else:
                raise Exception("Failed to connect to Deepgram")
                
        except Exception as e:
            logger.error(f"Failed to start Deepgram transcriber: {e}")
            if self._error_callback:
                self._error_callback(f"启动失败: {e}")
            raise
    
    async def stop(self):
        """Stop the transcription service."""
        self.is_running = False
        self.is_reconnecting = False  # Stop any reconnection attempts
        
        # Close WebSocket connection
        if self.connection:
            try:
                self.connection.finish()  # finish() is not async
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            self.connection = None
        
        # Stop polish processor
        if self.polish_task:
            await self.polish_queue.put(None)
            await self.polish_task
        
        logger.info("Deepgram transcription service stopped")
    
    async def _reconnect(self):
        """Attempt to reconnect to Deepgram."""
        if self.is_reconnecting or not self.is_running:
            return
            
        self.is_reconnecting = True
        
        while self.is_running and self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                self.reconnect_attempts += 1
                logger.info(f"Attempting to reconnect... (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})")
                
                # Close existing connection if any
                if self.connection:
                    try:
                        self.connection.finish()
                    except Exception:
                        pass
                    self.connection = None
                
                # Wait before reconnecting
                await asyncio.sleep(self.reconnect_delay)
                
                # Create new connection
                self.connection = self.deepgram.listen.live.v("1")
                
                # Re-configure event handlers
                self.connection.on(LiveTranscriptionEvents.Open, self._on_open)
                self.connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
                self.connection.on(LiveTranscriptionEvents.Metadata, self._on_metadata)
                self.connection.on(LiveTranscriptionEvents.Error, self._on_error)
                self.connection.on(LiveTranscriptionEvents.Close, self._on_close)
                self.connection.on(LiveTranscriptionEvents.UtteranceEnd, self._on_utterance_end)
                
                # Re-configure options
                options = LiveOptions(
                    model=self.model_name,
                    language=self.language,
                    punctuate=True,
                    smart_format=True,
                    interim_results=self.interim_results,
                    utterance_end_ms=1000,
                    vad_events=True,
                    endpointing=300,
                    encoding="linear16",
                    sample_rate=16000,
                    channels=1,
                )
                
                # Start connection
                if self.connection.start(options):
                    logger.info("Reconnection successful!")
                    self.reconnect_attempts = 0  # Reset counter on success
                    self.is_reconnecting = False
                    if self._transcription_callback:
                        # Notify about reconnection
                        reconnect_result = TranscriptionResult(
                            detected_language="system",
                            original_text="[Reconnected]",
                            chinese_translation="[重新连接成功]",
                            timestamp=datetime.now().strftime('%H:%M:%S'),
                            is_final=True
                        )
                        self._transcription_callback(reconnect_result)
                    return
                else:
                    raise Exception("Failed to reconnect")
                    
            except Exception as e:
                logger.error(f"Reconnection attempt failed: {e}")
                if self.reconnect_attempts >= self.max_reconnect_attempts:
                    logger.error("Max reconnection attempts reached. Giving up.")
                    if self._error_callback:
                        self._error_callback(f"无法重新连接: {e}")
                    self.is_running = False
                    break
                    
        self.is_reconnecting = False
    
    def send_audio(self, audio_data: bytes):
        """Send audio data to Deepgram for transcription."""
        if self.connection and self.is_running and self.connection_ready:
            try:
                self.connection.send(audio_data)
            except Exception as e:
                logger.error(f"Error sending audio: {e}")
                if self._error_callback:
                    self._error_callback(f"发送音频错误: {e}")
        else:
            if self.is_running:
                logger.warning(f"Cannot send audio - connection_ready: {self.connection_ready}, connection: {self.connection is not None}")
    
    def _on_open(self, *args):
        """Handle connection open event."""
        logger.info("Deepgram connection opened")
        self.connection_ready = True
        # logger.debug(f"Connection ready set to True")
    
    def _on_metadata(self, *args, metadata=None, **kwargs):
        """Handle metadata event."""
        if metadata:
            # logger.debug(f"Metadata: {metadata}")
            pass
    
    def _on_error(self, *args, error=None, **kwargs):
        """Handle error event."""
        logger.error(f"Deepgram error: {error}")
        self.connection_ready = False
        
        # Schedule reconnection if still running
        if self.is_running and self.main_loop and not self.is_reconnecting:
            logger.info("Scheduling reconnection due to error...")
            asyncio.run_coroutine_threadsafe(
                self._reconnect(),
                self.main_loop
            )
    
    def _on_close(self, *args, **kwargs):
        """Handle connection close event."""
        logger.info("Deepgram connection closed")
        self.connection_ready = False
        
        # Schedule reconnection if still running
        if self.is_running and self.main_loop and not self.is_reconnecting:
            logger.info("Scheduling reconnection due to connection close...")
            asyncio.run_coroutine_threadsafe(
                self._reconnect(),
                self.main_loop
            )
    
    def _on_utterance_end(self, *args, utterance_end=None, **kwargs):
        """Handle utterance end event - indicates end of a spoken phrase."""
        if utterance_end:
            # utterance_end is an object, not a dict
            last_word_end = getattr(utterance_end, 'last_word_end', 0)
            # logger.debug(f"Utterance ended at {last_word_end:.2f}s")
            # Could trigger additional processing here if needed
    
    def _on_transcript(self, *args, result=None, **kwargs):
        """Handle transcript event."""
        # logger.debug("_on_transcript called")
        if not result:
            logger.warning("No result in transcript event")
            return
        
        try:
            # Parse the transcript
            transcript = result.channel.alternatives[0].transcript
            is_final = result.is_final
            # logger.debug(f"Transcript received: '{transcript}', is_final={is_final}")
            
            if not transcript:
                # Still process empty transcripts for continuity
                if is_final:
                    # logger.debug("Empty final transcript received")
                    pass
                return
            
            if self.interim_results and not is_final:
                # For interim results, just update the pending text
                self.pending_text = transcript
                
                # Create an interim result without polish
                alt = result.channel.alternatives[0]
                langs = getattr(alt, "languages", None)
                detected_lang = langs[0] if langs else (self.language or "unknown")
                
                interim_result = TranscriptionResult(
                    detected_language=detected_lang,
                    original_text=transcript,
                    chinese_translation="",  # No translation for interim
                    timestamp=datetime.now().strftime('%H:%M:%S'),
                    is_final=False
                )
                
                # Send interim result immediately
                if self._transcription_callback:
                    self._transcription_callback(interim_result)
            
                # Check if should trigger translation (time threshold)
                current_time = datetime.now().timestamp()
                time_since_last = current_time - self.last_translation_time
                # logger.debug(f"Time since last translation: {time_since_last:.2f}s, threshold: {self.translation_threshold}s")
                
                if time_since_last >= self.translation_threshold:
                    # Update last translation time
                    self.last_translation_time = current_time
                    # logger.debug(f"Triggering translation due to time threshold")
                    
                    # Queue for translation
                    if self.main_loop:
                        asyncio.run_coroutine_threadsafe(
                            self._queue_for_polish(transcript, result),
                            self.main_loop
                        )
            
            elif is_final:
                # Clear pending text
                self.pending_text = ""
                # logger.debug(f"Received final transcript, triggering translation")
                
                # Always translate on final
                self.last_translation_time = datetime.now().timestamp()
                
                # Queue for translation
                if self.main_loop:
                    asyncio.run_coroutine_threadsafe(
                        self._queue_for_polish(transcript, result),
                        self.main_loop
                    )
                
        except Exception as e:
            logger.error(f"Error processing transcript: {e}")
            if self._error_callback:
                self._error_callback(f"处理转录错误: {e}")
    
    async def _queue_for_polish(self, transcript: str, result):
        """Queue transcript for polish and translation."""
        # Extract language from result
        alt = result.channel.alternatives[0]
        langs = getattr(alt, "languages", None)
        detected_lang = langs[0] if langs else (self.language or "unknown")
        
        # logger.debug(f"Queueing text for translation: '{transcript}' (lang: {detected_lang})")
        await self.polish_queue.put({
            'text': transcript,
            'language': detected_lang,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
    
    async def _polish_processor(self):
        """Process transcriptions for polish and translation."""
        logger.info("Polish processor started")
        
        while self.is_running:
            try:
                # Get transcript from queue
                item = await self.polish_queue.get()
                if item is None:
                    break
                
                # logger.debug(f"Processing translation for: '{item['text']}'")
                # Perform polish and translation
                result = await self._polish_transcription(
                    item['text'],
                    item['language'],
                    item['timestamp']
                )
                
                if result and self._transcription_callback:
                    # logger.debug(f"Translation result: '{result.chinese_translation}'")
                    self._transcription_callback(result)
                
            except Exception as e:
                logger.error(f"Error in polish processor: {e}")
                if self._error_callback:
                    self._error_callback(f"润色处理错误: {e}")
        
        logger.info("Polish processor stopped")
    
    async def _polish_transcription(self, text: str, language: str, timestamp: str) -> Optional[TranscriptionResult]:
        """Polish and translate transcription text."""
        try:
            # Build context
            context = self._build_context()
            
            messages = [
                {"role": "system", "content": """你是一个顶级的同声传译AI，专门处理实时的、碎片化的英文语音转录。你的核心任务是输出极其连贯、流畅的中文翻译。

**你的工作流程是“合并与修正”，而不是简单的“独立翻译”。**

你的核心任务是：
1.  **合并与修正 (Merge & Revise)**：这是你的首要规则。当“当前新文本”是“上一句”的延续时，你**必须**在“上一句的最终翻译”的基础上进行修改、扩展或润色，形成一句完整的话。**不要**为延续性的文本片段生成一个全新的、独立的句子。
2.  **另起新句 (Start New)**：如果“当前新文本”在语义上明显开启了一个新的话题或句子，你才应该输出一个新的、独立的翻译。
3.  **纠正明显的识别错误**：利用上下文修正语音识别的错误如P vs MP应为P vs NP 
4.  **简洁与自然 (Concise & Natural)**：翻译结果要简短、口语化，符合中文母语者的习惯。字幕长度尽量控制在20-25个汉字以内。
5.  **格式要求**：只返回一个JSON对象，包含`chinese_translation`字段。不要添加任何解释或markdown标记。

**关键指令示例 (Few-Shot Example):**

这是一个如何执行“合并与修正”的完美范例：

*   **输入:**
    *   `上一句的原始文本`: "sure. I mean, we you know, maybe we should talk about the origins of life too,"
    *   `上一句的最终翻译`: "当然，我们也许也该谈谈生命的起源"
    *   `当前收到的新文本`: "but proteins themselves, I think, are magical."

*   **你的思考过程:** 我看到“当前新文本” (`but proteins themselves...`) 在语义上紧跟“上一句的原始文本” (`...origins of life too,`)，它们共同构成了一个更长的句子。因此，我的任务不是独立翻译新文本，而是必须将它的意思合并到“上一句的最终翻译”中，使其更完整。

*   **正确的JSON输出:**
    ```json
    {
        "chinese_translation": "当然，我们也该谈谈生命的起源，但我认为蛋白质本身就非常神奇"
    }
    ```

"""},
                {"role": "user", "content": f"""

参考上下文：
{context}

请翻译以下转录文本，并确保与上下文连贯：
当前文本: {text}（需要翻译）


只返回JSON，不要有其他内容：
{{
    "chinese_translation": "连贯的中文翻译"
}}"""}
            ]
            
            # Get polish and translation
            completion = await asyncio.to_thread(
                self.polish_client.chat.completions.create,
                model=self.polish_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=2048
            )
            
            # Parse response
            try:
                result_data = json.loads(completion.choices[0].message.content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                logger.error(f"Raw response: {completion.choices[0].message.content}")
                # Try to extract translation from malformed response
                import re
                match = re.search(r'"chinese_translation"\s*:\s*"([^"]+)"', completion.choices[0].message.content)
                if match:
                    result_data = {"chinese_translation": match.group(1)}
                else:
                    result_data = {"chinese_translation": ""}
            
            # Create result
            result = TranscriptionResult(
                detected_language=language,
                original_text=text,
                chinese_translation=result_data.get('chinese_translation', ''),
                timestamp=timestamp,
                is_final=True
            )
            
            # Add to context
            self.recent_transcriptions.append(result)
            if len(self.recent_transcriptions) > self.context_window:
                self.recent_transcriptions = self.recent_transcriptions[-self.context_window:]
            
            return result
            
        except Exception as e:
            logger.error(f"Polish error: {e}")
            # Return untranslated result on error
            return TranscriptionResult(
                detected_language=language,
                original_text=text,
                chinese_translation='',
                timestamp=timestamp,
                is_final=True
            )
    
    def _build_context(self) -> str:
        """Build context from recent transcriptions."""
        if not self.recent_transcriptions:
            return "这是对话的开始。"
        
        # Take last few transcriptions
        context_items = self.recent_transcriptions[-5:]
        context_parts = []
        
        # Build context with both original and translation
        for i, item in enumerate(context_items, 1):
            context_part = f"前{len(context_items) - i + 1}条:"
            context_part += f"\n原文: {item.original_text}"
            if item.chinese_translation:
                context_part += f"\n翻译: {item.chinese_translation}"
            context_parts.append(context_part)
        
        return "参考上下文（从旧到新）:\n" + "\n\n".join(context_parts)