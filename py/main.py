import sys
import logging
from time import sleep
sys.path.append('../')

from samsungtvws import SamsungTVWS

# Increase debug level
logging.basicConfig(level=logging.INFO)

# Normal constructor
tv = SamsungTVWS('10.0.1.111')

# Is art mode supported?
# info = tv.art().supported()
# logging.info(info)

# List the art available on the device
# info = tv.art().available()
# logging.info(info)

# Retrieve information about the currently selected art
# info = tv.art().get_current()
# logging.info(info)

# # Retrieve a thumbnail for a specific piece of art. Returns a JPEG.
# thumbnail = tv.art().get_thumbnail('SAM-F0206')

# # Set a piece of art
# tv.art().select_image('SAM-F0206')

# # Set a piece of art, but don't immediately show it if not in art mode
# tv.art().select_image('SAM-S10002300', show=True)
# sleep(5)
# # Determine whether the TV is currently in art mode
# info = tv.art().get_artmode()
# logging.info(info)

# Switch art mode on or off
# tv.art().set_artmode(True)
# tv.art().set_artmode(False)

# # # Upload a picture
file = open('/Users/sjoerdbolten/Documents/Projects/tijdvorm/py/adsdsadsa.png', 'rb')
data = file.read()
content_id  = tv.art().upload(data, matte='shadowbox_polar')
print(content_id)
sleep(2)
print(tv.art().select_image(content_id, show=True))

# # If uploading a JPEG
# tv.art().upload(data, file_type='JPEG')

# # To set the matte to modern and apricot color

# # Delete an uploaded item
# tv.art().delete('MY-F0020')

# # Delete multiple uploaded items
# tv.art().delete_list(['MY-F0020', 'MY-F0021'])

# # List available photo filters
# info = tv.art().get_photo_filter_list()
# logging.info(info)

# # Apply a filter to a specific piece of art
# tv.art().set_photo_filter('SAM-F0206', 'ink')