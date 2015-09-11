import numpy as np

# Enthought library imports.
from traits.api import Unicode, Str, Int, Bool, Any, Set

from ..library import rect, coordinates
from ..renderer import color_floats_to_int, int_to_color_floats, int_to_html_color_string, alpha_from_int, ImageData

from base import ProjectedLayer

from maproom.library import numpy_images

import logging
log = logging.getLogger(__name__)

class WMSLayer(ProjectedLayer):
    """Web Map Service
    
    """
    name = Unicode("WMS")
    
    type = Str("wms")
    
    layer_info_panel = ["Map server", "Map layer"]
    
    map_server_id = Int(0)
    
    map_layers = Set(Str)
    
    image_data = Any
    
    current_size = Any(None)  # holds tuple of screen size
    
    current_proj = Any(None)  # holds rect of projected coords
    
    current_world = Any(None)  # holds rect of world coords
    
    rebuild_needed = Bool(True)
    
    threaded_request_ready = Any(None)
    
    checkerboard_when_loading = False
    
    def get_image_array(self):
        if self.threaded_request_ready is None:
            return self.current_world, numpy_images.get_checkerboard(*self.current_size)
        else:
            wms_result = self.threaded_request_ready
            self.threaded_request_ready = None
            return wms_result.world_rect, wms_result.get_image_array()

    def rebuild_renderer(self, renderer, in_place=False):
        projection = self.manager.project.layer_canvas.projection
        if self.rebuild_needed:
            renderer.release_textures()
            self.image_data = None
        if self.image_data is None and self.current_size is not None:
            world_rect, raw = self.get_image_array()
            self.image_data = ImageData(raw.shape[0], raw.shape[1])
            self.image_data.load_numpy_array(None, raw)
            # OpenGL y coords are backwards, so simply flip world y coords and
            # OpenGL handles it correctly.
            flipped = ((world_rect[0][0], world_rect[1][1]),
                       (world_rect[1][0], world_rect[0][1]))
            self.image_data.set_rect(flipped, None)
            print "setting image data from wms connection:", world_rect
        if self.image_data is not None:
            renderer.set_image_projection(self.image_data, projection)
            self.rebuild_needed = False

    def resize(self, renderer, world_rect, proj_rect, screen_rect):
        print "world_rect = %r" % (world_rect,)
        print "proj_rect = %r" % (proj_rect,)
        print "screen_rect = %r" % (screen_rect,)
        old_size = self.current_size
        old_world = self.current_world
        self.current_size = rect.size(screen_rect)
        self.current_proj = ((proj_rect[0][0], proj_rect[0][1]), (proj_rect[1][0], proj_rect[1][1]))
        self.current_world = ((world_rect[0][0], world_rect[0][1]), (world_rect[1][0], world_rect[1][1]))
        if old_size is not None:
            if old_size != self.current_size or old_world != self.current_world:
                renderer.canvas.set_minimum_delay_callback(self.wms_rebuild, 1000)
        else:
            # first time, load map immediately
            self.wms_rebuild(renderer.canvas)
            self.rebuild_needed = True
    
    def wms_rebuild(self, canvas):
        downloader = self.manager.project.task.get_threaded_wms_by_id(self.map_server_id)
        if downloader.is_valid():
            if not self.map_layers:
                self.map_layers = set(downloader.wms.get_default_layers())
                canvas.project.update_info_panels(self, True)
            layers = list(self.map_layers)
            downloader.request_map(self.current_world, self.current_proj, self.current_size, layers, self.manager, self)
            if self.checkerboard_when_loading:
                self.rebuild_needed = True
                canvas.render()
        else:
            # Try again, waiting till we get a successful contact
            if not downloader.wms.has_error():
                print "WMS not initialized yet, waiting..."
                self.change_count += 1  # Force info panel update
                canvas.set_minimum_delay_callback(self.wms_rebuild, 200)
            else:
                print "WMS error, not attempting to contact again"
    
    def change_server_id(self, id, canvas):
        if id != self.map_server_id:
            self.map_server_id = id
            self.map_layers = set()
            self.wms_rebuild(canvas)
            self.change_count += 1  # Force info panel update
            canvas.project.update_info_panels(self, True)

    def pre_render(self, renderer, world_rect, projected_rect, screen_rect):
        self.resize(renderer, world_rect, projected_rect, screen_rect)
        if self.rebuild_needed:
            self.rebuild_renderer(renderer)

    def render_projected(self, renderer, world_rect, projected_rect, screen_rect, layer_visibility, layer_index_base, picker):
        if picker.is_active:
            return
        log.log(5, "Rendering wms!!! pick=%s" % (picker))
        if self.image_data is not None:
            renderer.draw_image(layer_index_base, picker, 1.0)
