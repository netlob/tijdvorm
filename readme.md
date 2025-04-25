# tijdvorm

script to publish live art to samsung the frame tvs, using local weather data and some nice graphics

![Example Output](images/example.png)

## credits

the artwork of this project has been skillfully vibe coded by https://x.com/joonasvirtanen

## disclaimer

i hate python so i blind vibe coded this project using cursor/gemini. no guarantees this wont fuck up your tv.

## how to run

1. install deps (for >2022 frame models use this pip git by @NickWaterton, otherwise use the regular "samsungtvws")

```bash
pip install "git+https://github.com/NickWaterton/samsung-tv-ws-api.git#egg=samsungtvws[async,encrypted]" playwright asyncio PIL requests logging &&
playwright install chromium --with-deps
```

2. configure the script to use your tv's ip and optionally the weatherapi location
   note that your TV must be on the same exact network as this host, VLANs are not allowed by samsung
   also note the `DELETE_OLD_ART` parameter, which will make sure the TV doesnt get overloaded with art images which are never deleted (by default 1 image every minute)
3. run `python main.py`
