import logging
try:
    import upnpclient
except ImportError:
    upnpclient = None

from backend.config import TV_IP

# Configure logging
logger = logging.getLogger(__name__)

def play_url_via_dlna(url: str, tv_ip: str = TV_IP) -> bool:
    """
    Attempts to play a video URL on the TV using DLNA (AVTransport).
    """
    if upnpclient is None:
        logger.error("upnpclient is not installed. Cannot use DLNA.")
        return False

    try:
        logger.info(f"Scanning for UPnP devices to find TV at {tv_ip}...")
        # Note: upnpclient.discover() might be slow or unreliable if multicast is blocked.
        # But we don't have a way to direct connect easily with this lib without discovery first?
        # Actually, we can construct the device if we know the description URL.
        # Samsung TVs usually live at http://<ip>:9197/dmr or similar.
        
        devices = upnpclient.discover()
        
        target_device = None
        for dev in devices:
            try:
                # Basic check for friendly name or location
                # Wrap in try/except because accessing attributes on malformed devices can raise errors
                if tv_ip in dev.location:
                    target_device = dev
                    break
                if "Samsung" in dev.friendly_name and "Frame" in dev.friendly_name:
                    target_device = dev
                    break
            except Exception:
                continue
        
        if not target_device:
            logger.warning(f"Could not find DLNA device at {tv_ip}")
            # Try fallback: assume standard Samsung DMR port
            # device = upnpclient.Device(f"http://{tv_ip}:9197/dmr") # This might not work directly
            return False

        logger.info(f"Found DLNA device: {target_device.friendly_name}")
        
        # Find AVTransport service
        av_transport = target_device.AVTransport
        if not av_transport:
            logger.error("Device does not support AVTransport")
            return False

        # Stop current playback
        try:
            av_transport.Stop(InstanceID=0)
        except Exception:
            pass # Might not be playing

        # Set URI
        # Samsung might require specific metadata or mimetype in protocol info
        # protocolInfo="http-get:*:video/mp4:*" or similar
        # For HLS: "http-get:*:application/vnd.apple.mpegurl:*"
        
        # Construct DIDL-Lite Metadata
        if url.endswith(".jpg") or url.endswith(".jpeg"):
            protocol_info = "http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG;DLNA.ORG_OP=01;DLNA.ORG_FLAGS=01700000000000000000000000000000"
            upnp_class = "object.item.imageItem"
        else:
            protocol_info = "http-get:*:video/vnd.dlna.mpeg-tts:DLNA.ORG_OP=01;DLNA.ORG_FLAGS=01700000000000000000000000000000"
            upnp_class = "object.item.videoItem"

        didl_lite = (
            '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
            '<item id="0" parentID="-1" restricted="1">'
            '<dc:title>Doorbell Stream</dc:title>'
            f'<upnp:class>{upnp_class}</upnp:class>'
            f'<res protocolInfo="{protocol_info}">' + url + '</res>'
            '</item>'
            '</DIDL-Lite>'
        )

        logger.info(f"Setting AVTransportURI to {url}")
        av_transport.SetAVTransportURI(
            InstanceID=0,
            CurrentURI=url,
            CurrentURIMetaData=didl_lite
        )

        # Play
        logger.info("Sending Play command...")
        av_transport.Play(InstanceID=0, Speed="1")
        
        return True

    except Exception as e:
        logger.error(f"DLNA streaming failed: {e}")
        return False

def stop_dlna(tv_ip: str = TV_IP):
    if upnpclient is None:
        return

    try:
        devices = upnpclient.discover()
        target_device = None
        for dev in devices:
            if tv_ip in dev.location:
                target_device = dev
                break
        
        if target_device and hasattr(target_device, 'AVTransport'):
            target_device.AVTransport.Stop(InstanceID=0)
    except Exception:
        pass

