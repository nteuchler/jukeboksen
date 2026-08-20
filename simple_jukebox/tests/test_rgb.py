from simple_jukebox.rgb import SIDE_LENGTH, level_to_height


def test_equalizer_uses_full_range_and_preserves_amplitude_changes():
    heights = [
        level_to_height(10 ** (decibels / 20))
        for decibels in (-60, -55, -50, -45, -40, -35, -30, -28)
    ]

    assert heights == sorted(heights)
    assert heights[0] == 0
    assert heights[2] >= 10
    assert heights[-1] == SIDE_LENGTH
