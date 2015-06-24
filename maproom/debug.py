def debug_objects(lm):
    import layers
#    a = layers.OverlayImageObject(manager=lm)
#    a.set_location((-16.6637485204,-1.40163099748))
#    a.set_style(lm.default_style)
#    lm.insert_layer([2], a)
#    
#    a = layers.OverlayTextObject(manager=lm)
#    a.set_location((6.6637485204,-1.40163099748))
#    a.set_style(lm.default_style)
#    lm.insert_layer([2], a)
    
    a = layers.ScaledImageObject(manager=lm)
    #a = layers.RectangleVectorObject(manager=lm)
    a.set_opposite_corners(
        (-16.6637485204,-1.40163099748),
        (9.65688930428,-19.545688433))
    a.set_style(lm.default_style)
    lm.insert_layer([2], a)
    
#    a = layers.PolylineObject(manager=lm)
#    a.set_points([
#        (-15,-2),
#        (5, -8),
#        (10, -20),
#        (8, -5),
#        (-17, -10),
#        ])
#    a.set_style(lm.default_style)
#    a.style.fill_style = 0
#    lm.insert_layer([2], a)