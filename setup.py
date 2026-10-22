"""Keep repeated wheel builds free of obsolete fingerprinted web assets."""

from pathlib import Path
from shutil import rmtree

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    """Clear only this package's generated asset copy before collecting data."""

    def run(self):
        assets = Path(self.build_lib) / "aethel_web" / "static"
        if assets.exists():
            rmtree(assets)
        super().run()


setup(cmdclass={"build_py": BuildPy})
