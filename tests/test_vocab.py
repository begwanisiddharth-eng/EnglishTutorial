"""The working vocabulary list and the master-list build script."""
import subprocess
import sys
from pathlib import Path

import vocab

ROOT = Path(__file__).parent.parent


def test_fold_ignores_case_accents_and_ligatures():
    assert vocab.fold("Œuvre") == vocab.fold("oeuvre")
    assert vocab.fold("FAÇADE") == vocab.fold("facade")


def test_word_phrase_boundary():
    assert not vocab.is_phrase("zephyr")
    assert vocab.is_phrase("a babe in the woods")


def test_remove_and_restore_match_loosely():
    vocab.remove("ABASE")
    assert "abase" not in vocab.load_remaining()
    vocab.restore("Abase")
    assert "abase" in vocab.load_remaining()
    vocab.restore("not in the master list")
    assert len(vocab.load_remaining()) == 5000


def test_build_vocab_runs_from_any_folder(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "build_vocab.py")], cwd=tmp_path,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "words: 3500/3500  phrases: 1500/1500" in result.stdout
