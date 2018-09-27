from fs.opener import opener
from osgeo import ogr
ogr.UseExceptions()

from traits.api import HasTraits, provides

from omnivore.file_type.i_file_recognizer import IFileRecognizer, RecognizerBase

import logging
log = logging.getLogger(__name__)


@provides(IFileRecognizer)
class OGRRecognizer(RecognizerBase):
    """Check to see if OGR can open this as a vector shapefile.

    """
    id = "application/x-maproom-shapefile"

    before = "text/*"

    def identify(self, guess):
        try:
            fs, relpath = opener.parse(guess.metadata.uri)
            if not fs.hassyspath(relpath):
                return None
            file_path = fs.getsyspath(relpath)
            if file_path.startswith("\\\\?\\"):  # GDAL doesn't support extended filenames
                file_path = file_path[4:]
            dataset = ogr.Open(file_path)
        except RuntimeError:
            log.debug("OGR can't open %s; not an image")
            return None
        if dataset is not None and dataset.GetLayerCount() > 0:
            # check to see if there are any valid layers because some CSV files
            # seem to be recognized as having layers but have no geometry.
            count = 0
            for layer_index in range(dataset.GetLayerCount()):
                layer = dataset.GetLayer(layer_index)
                for feature in layer:
                    ogr_geom = feature.GetGeometryRef()
                    print(f"ogr_geom for {layer} = {ogr_geom}")
                    if ogr_geom is None:
                        continue
                    count += 1
            if count > 0:
                return self.id
        return None
