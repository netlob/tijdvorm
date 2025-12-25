import sys
import time
import logging
from time import sleep
# sys.path.append('../')

# from samsungtvws import SamsungTVWS


# sys.path.insert(0, '/Users/sjoerdbolten/Documents/fungits/samsung-tv-ws-api')

from samsungtvws import SamsungTVWS

# Increase debug level
logging.basicConfig(level=logging.INFO)

print('connecting to tv')
start_time = time.time()
# Normal constructor
tv = SamsungTVWS('10.0.1.111')
print('connected to tv in', time.time() - start_time, 'seconds')

# Is art mode supported?
info = tv.art().supported()
logging.info(info)

# List the art available on the device
# info = tv.art().available()
# logging.info(info)

# # Retrieve information about the currently selected art
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
info = tv.art().get_artmode()
logging.info(info)

# Switch art mode on or off
# tv.art().set_artmode(True)
# tv.art().set_artmode(False)

# # # Upload a picture
# start_time = time.time()
# print('uploading art')
# file = open('rotated_freaky_bob.png', 'rb')
# data = file.read()
# content_id  = tv.art().upload(data, matte='none')
# print('uploaded art in', time.time() - start_time, 'seconds')

# content_id = 'MY_F19168' # boef
content_id = 'MY_F18998' # boef
# content_id = 'MY_F19055' # clock
start_time = time.time()
print('setting art to', content_id)
print(tv.art().select_image(content_id, show=True))
print('set art to', content_id, 'took ', time.time() - start_time, 'seconds')

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