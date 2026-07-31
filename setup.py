import sys
from pathlib import Path

from setuptools import setup
from py2app.build_app import py2app as py2app_command


class AppBuild(py2app_command):
    def finalize_options(self):
        # uv installs the declared project dependencies before this command.
        # py2app 0.28 rejects setuptools' PEP 621 install_requires metadata.
        self.distribution.install_requires = []
        super().finalize_options()


APP = ["app.py"]
PYTHON_LIBRARY_DIR = Path(sys.base_prefix) / "lib"
SITE_PACKAGES_DIR = (
    Path(sys.prefix)
    / "lib"
    / f"python{sys.version_info.major}.{sys.version_info.minor}"
    / "site-packages"
)
MYPYC_MODULES = [
    path.name.split(".", 1)[0]
    for path in SITE_PACKAGES_DIR.glob("*__mypyc*.so")
]
PYTHON_LIBRARY_NAMES = (
    "libbz2.dylib",
    "libcrypto.3.dylib",
    "libffi.8.dylib",
    "liblzma.5.dylib",
    "libncursesw.6.dylib",
    "libssl.3.dylib",
    "libtcl8.6.dylib",
    "libtinfow.6.dylib",
    "libtk8.6.dylib",
    "libz.1.dylib",
)
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/AppIcon.icns",
    "includes": [
        "tiktoken_ext.openai_public",
        *MYPYC_MODULES,
    ],
    "frameworks": [
        str(PYTHON_LIBRARY_DIR / name)
        for name in PYTHON_LIBRARY_NAMES
        if (PYTHON_LIBRARY_DIR / name).exists()
    ],
    "resources": [
        "assets",
        "config.ini.example",
    ],
    "plist": {
        "CFBundleName": "Mac Live Subtitle",
        "CFBundleDisplayName": "Mac Live Subtitle",
        "CFBundleIdentifier": "com.henryjessie.MacLiveSubtitle",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSApplicationCategoryType": "public.app-category.utilities",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSScreenCaptureUsageDescription": (
            "Mac Live Subtitle captures system audio to generate live subtitles."
        ),
    },
}


setup(
    name="Mac Live Subtitle",
    version="0.1.0",
    app=APP,
    options={"py2app": OPTIONS},
    cmdclass={"py2app": AppBuild},
)
