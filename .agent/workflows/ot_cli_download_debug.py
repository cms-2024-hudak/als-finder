import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
logging.basicConfig(level=logging.DEBUG)

from als_finder.cli import download
from click.testing import CliRunner

runner = CliRunner()
result = runner.invoke(download, ['--workspace', 'scratch/TAHOE_OT_3', '--roi', './examples/ltbmu_boundary.gpkg', '--name', '~^Lake Tahoe Basin', '--ot-key', 'dummy'])
print("Exit Code:", result.exit_code)
print("Output:", result.output)
if result.exception:
    import traceback
    traceback.print_exception(type(result.exception), result.exception, result.exception.__traceback__)
