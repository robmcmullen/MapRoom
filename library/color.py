import numpy as np


def color_to_int(red, green, blue, alpha):
    """
    Given individual channel values for a color from 0.0 to 1.0, return that
    color as a single integer RGBA value.

    :param red: red channel value
    :type red: float
    :param green: green channel value
    :type green: float
    :param blue: blue channel value
    :type blue: float
    :param alpha: alpha channel value
    :type alpha: float
    :return: combined RGBA color value
    :rtype: uint32
    """
    CHANNEL_MAX = 255.0

    return np.array(
        (
            int(red * CHANNEL_MAX),
            int(green * CHANNEL_MAX),
            int(blue * CHANNEL_MAX),
            int(alpha * CHANNEL_MAX),
        ),
        dtype=np.uint8,
    ).view(np.uint32)[0]

def int_to_color(color):
    ints = np.frombuffer(color.tostring(), dtype=np.uint8)
    floats = tuple([i/255.0 for i in ints])
    return floats

if __name__ == "__main__":
    rgba = (.5, .5, .5, 1)
    i = color_to_int(*rgba)
    print "%x" % i
    print type(i)
    color = int_to_color(i)
    rgba2 = list(color)
    print rgba2
