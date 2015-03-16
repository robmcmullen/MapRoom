driver="vispy"

if driver == "gl":
    from .gl.renderer_driver import RendererDriver
    from .gl.layer_renderer import LayerRenderer
    from .gl.parser import *
    from .gl.color import color_to_int, int_to_color
    import gl.data_types as data_types
    from .gl.base_canvas import BaseCanvas
else:
    from .vispy.renderer_driver import RendererDriver
    from .vispy.layer_renderer import LayerRenderer
    from .vispy.parser import *
    from .vispy.color import color_to_int, int_to_color
    import gl.data_types as data_types
    from .vispy.base_canvas import BaseCanvas
    
