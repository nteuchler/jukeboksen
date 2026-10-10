import subprocess
import sys


def test_local_log_flushes_at_exit_and_rotates(tmp_path):
    subprocess.run([sys.executable, "-c", """
import logging, sys
from simple_jukebox.diagnostics import configure_logging
configure_logging(sys.argv[1])
configure_logging(sys.argv[1])
logger = logging.getLogger('simple_jukebox.test')
logger.info('unique startup marker')
for _ in range(25):
    logger.info('x' * 100000)
try:
    raise RuntimeError('hardware failure example')
except RuntimeError:
    logger.exception('captured failure')
""", str(tmp_path)], check=True)
    current = (tmp_path / "jukebox.log").read_text()
    previous = (tmp_path / "jukebox.log.1").read_text()
    assert previous.count("unique startup marker") == 1
    assert "RuntimeError: hardware failure example" in current
    assert "Z INFO pid=" in previous
    assert (tmp_path / "jukebox.log").stat().st_size < 2_000_000
