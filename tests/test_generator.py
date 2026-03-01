# tests/test_generator.py
import pytest
import tempfile
import os
import json
from unittest.mock import patch, MagicMock
from merkaba.generation.generator import ImageGenerator


def test_generator_creates_output_dir():
    """Generator should create output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = os.path.join(tmpdir, "outputs")
        generator = ImageGenerator(output_dir=output_dir)
        assert os.path.exists(output_dir)


def test_generate_creates_run_folder():
    """generate should create a folder for the generation run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_dir = os.path.join(tmpdir, "workflows")
        output_dir = os.path.join(tmpdir, "outputs")
        os.makedirs(workflow_dir)

        # Create a minimal workflow
        workflow = {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "PROMPT_PLACEHOLDER"}}}
        with open(os.path.join(workflow_dir, "clipart.json"), "w") as f:
            json.dump(workflow, f)

        generator = ImageGenerator(output_dir=output_dir, workflow_dir=workflow_dir)

        with patch.object(generator, "_client") as mock_client:
            mock_client.check_connection.return_value = True
            mock_client.queue_prompt.return_value = "test-id"
            mock_client.wait_for_completion.return_value = {
                "outputs": {"9": {"images": [{"filename": "test.png", "subfolder": "", "type": "output"}]}}
            }
            mock_client.get_image.return_value = b"fake image data"

            result = generator.generate("test prompt", workflow_type="clipart")

            assert os.path.exists(result["output_dir"])
            assert "metadata.json" in os.listdir(result["output_dir"])


def test_generate_saves_metadata():
    """generate should save metadata.json with prompt and settings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_dir = os.path.join(tmpdir, "workflows")
        output_dir = os.path.join(tmpdir, "outputs")
        os.makedirs(workflow_dir)

        workflow = {"6": {"class_type": "CLIPTextEncode", "inputs": {"text": "PROMPT_PLACEHOLDER"}}}
        with open(os.path.join(workflow_dir, "clipart.json"), "w") as f:
            json.dump(workflow, f)

        generator = ImageGenerator(output_dir=output_dir, workflow_dir=workflow_dir)

        with patch.object(generator, "_client") as mock_client:
            mock_client.check_connection.return_value = True
            mock_client.queue_prompt.return_value = "test-id"
            mock_client.wait_for_completion.return_value = {
                "outputs": {"9": {"images": [{"filename": "test.png", "subfolder": "", "type": "output"}]}}
            }
            mock_client.get_image.return_value = b"fake image data"

            result = generator.generate("boho clipart", workflow_type="clipart")

            metadata_path = os.path.join(result["output_dir"], "metadata.json")
            with open(metadata_path) as f:
                metadata = json.load(f)

            assert metadata["prompt"] == "boho clipart"
            assert metadata["workflow_type"] == "clipart"


def test_generate_raises_when_comfyui_offline():
    """generate should raise error when ComfyUI is not running."""
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = ImageGenerator(output_dir=tmpdir)

        with patch.object(generator, "_client") as mock_client:
            mock_client.check_connection.return_value = False

            with pytest.raises(RuntimeError, match="ComfyUI"):
                generator.generate("test", workflow_type="clipart")
