#!/usr/bin/env python
import os
import shutil
import subprocess

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

def publish():
    # clean
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    
    # build
    run("python -m build")
    
    # upload
    run("twine upload dist/*")
    
    # tag
    version = __import__("cloudoll").__version__
    run(f"git tag v{version}")
    run("git push --tags")

if __name__ == "__main__":
    publish()