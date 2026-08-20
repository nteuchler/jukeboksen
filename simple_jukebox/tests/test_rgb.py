from simple_jukebox.rgb import SIDE_LENGTH, level_to_height


def test_equalizer_uses_full_range_and_preserves_amplitude_changes():
    heights = [
        level_to_height(10 ** (decibels / 20))
        for decibels in (-28, -26, -24, -20, -16, -13, -11)
    ]

    assert heights == sorted(heights)
    assert heights[0] == 0
    assert 12 <= heights[3] <= 16
    assert heights[5] >= 25
    assert heights[-1] == SIDE_LENGTH
