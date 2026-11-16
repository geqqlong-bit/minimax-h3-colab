"""Execute notebook download/activation logic without GPU or network dependencies."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

NOTEBOOK = Path(__file__).resolve().parents[2] / "H3_Toybox.ipynb"


def cell_source(prefix):
    for cell in json.loads(NOTEBOOK.read_text())["cells"]:
        source = cell["source"]
        source = "".join(source) if isinstance(source, list) else source
        if source.startswith(prefix):
            return source
    raise AssertionError(f"Missing notebook cell: {prefix}")


class VoiceNotebookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.voice = self.root / "indextts2"
        self.voice.mkdir()
        self.cfg = {"enabled": True, "python": str(self.voice / "python"),
                    "model_dir": str(self.voice / "checkpoints"), "repo_dir": str(self.voice / "source")}
        for name in ("python", "checkpoints/config.yaml", "source/indextts/infer_v2.py"):
            p = self.voice / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()

    def path(self, value):
        path = Path(value)
        return self.root / path.relative_to("/content") if path.is_relative_to("/content") else path

    def manifest(self):
        (self.voice / "toybox_voice_config.json").write_text(json.dumps(self.cfg))

    def activate(self, **extra):
        source = cell_source("#@title ③ ")
        start = source.index("voice_manifest =")
        end = source.index("cfg['voice_clone'] = voice_cfg", start) + len("cfg['voice_clone'] = voice_cfg")
        scope = {"Path": self.path, "json": json, "cfg": {}, "print": Mock(), **extra}
        exec(compile(source[start:end], "notebook-voice-activation", "exec"), scope)
        return scope["cfg"]["voice_clone"]

    def test_ready_models_enable_without_previous_checkbox_variable(self):
        self.manifest()
        self.assertTrue(self.activate()["enabled"])

    def test_no_manifest_is_disabled_and_explicit_skip_is_respected(self):
        self.assertFalse(self.activate()["enabled"])
        self.manifest()
        self.assertFalse(self.activate(INSTALL_VOICE_CLONE=False)["enabled"])

    def test_missing_model_requests_the_download_cell(self):
        self.manifest()
        (self.voice / "checkpoints/config.yaml").unlink()
        with self.assertRaisesRegex(RuntimeError, "②-b"):
            self.activate()

    def test_dedicated_download_cell_defaults_on_and_calls_real_installer(self):
        source = cell_source("#@title ②-b ")
        tree = ast.parse(source)
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        installer = self.root / "minimax-h3-colab/tools/install_indextts2.py"
        installer.parent.mkdir(parents=True)
        installer.touch()
        run = Mock(side_effect=lambda *args, **kwargs: self.manifest())
        scope = {"Path": self.path, "json": json, "sys": sys,
                 "subprocess": type("Commands", (), {"run": run}), "print": Mock()}
        exec(compile(tree, "notebook-voice-download", "exec"), scope)
        self.assertTrue(scope["INSTALL_VOICE_CLONE"])
        run.assert_called_once_with([sys.executable, str(installer), "--root", str(self.voice)], check=True)


if __name__ == "__main__":
    unittest.main()
