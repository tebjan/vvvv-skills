from vl_patch_manipulator.benchmark import main


def test_benchmark_needs_no_private_repository(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "valid=True" in output
    assert "add_connect_ms=" in output
    assert "change_feed_ms=" in output
