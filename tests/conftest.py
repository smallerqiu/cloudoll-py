import os
import tempfile

# Library logging must not write into the developer's home during tests.
os.environ["CLOUDOLL_LOG_DIR"] = tempfile.mkdtemp(prefix="cloudoll-tests-")
