- Test all settings
- Test setup
- Test OIDC
Implement blink-bridge
- Test clip/thumbnail retention
- Test NFS
- reset button
Log battery levels in graph
Log online/offline in graph
Should we use a database at this point instead of relying on flat files?

We need to update the cameras and syncs with how long and how often to snooze or arm a camera or sync as well as how often to take a thumnail. we should also offer a way to specify when to start snoozing or arming. so for example, if i want to snooze/arm barn driveway left for 4 hours every 4 hours on the hour, there should be a way to set this. if i want to do it at 27minutes of each hour i should be able to specify that. make it intuitive




myblink  | 2026-02-15 13:52:21 - werkzeug - INFO - 172.18.0.1 - - [15/Feb/2026 13:52:21] "POST /api/setup/admin HTTP/1.1" 200 -
myblink  | 2026-02-15 13:52:21 - web_server - ERROR - Exception on / [GET]
myblink  | Traceback (most recent call last):
myblink  |   File "/usr/local/lib/python3.12/site-packages/flask/app.py", line 1455, in wsgi_app
myblink  |     response = self.full_dispatch_request()
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/flask/app.py", line 869, in full_dispatch_request
myblink  |     rv = self.handle_user_exception(e)
myblink  |          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/flask/app.py", line 867, in full_dispatch_request
myblink  |     rv = self.dispatch_request()
myblink  |          ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/flask/app.py", line 852, in dispatch_request
myblink  |     return self.ensure_sync(self.view_functions[rule.endpoint])(**view_args)
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/app/modules/auth.py", line 611, in decorated_function
myblink  |     if current_user.is_authenticated:
myblink  |        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/werkzeug/local.py", line 318, in __get__
myblink  |     obj = instance._get_current_object()
myblink  |           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/werkzeug/local.py", line 526, in _get_current_object
myblink  |     return get_name(local())
myblink  |                     ^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/flask_login/utils.py", line 25, in <lambda>
myblink  |     current_user = LocalProxy(lambda: _get_user())
myblink  |                                       ^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/flask_login/utils.py", line 370, in _get_user
myblink  |     current_app.login_manager._load_user()
myblink  |   File "/usr/local/lib/python3.12/site-packages/flask_login/login_manager.py", line 347, in _load_user
myblink  |     raise Exception(
myblink  | Exception: Missing user_loader or request_loader. Refer to http://flask-login.readthedocs.io/#how-it-works for more info.
myblink  | 2026-02-15 13:52:21 - werkzeug - INFO - 172.18.0.1 - - [15/Feb/2026 13:52:21] "GET / HTTP/1.1" 500 -
myblink  | 2026-02-15 13:52:21 - werkzeug - INFO - 172.18.0.1 - - [15/Feb/2026 13:52:21] "GET /favicon.ico HTTP/1.1" 404 -
myblink  | 2026-02-15 13:52:22 - werkzeug - INFO - 172.18.0.1 - - [15/Feb/2026 13:52:22] "GET /sw.js HTTP/1.1" 200 -
Gracefully Stopping... press Ctrl+C again to force
 Container myblink  Stopping
myblink  | 2026-02-15 13:52:47 - __main__ - INFO - Received signal SIGTERM, initiating shutdown
myblink  | 2026-02-15 13:52:51 - __main__ - INFO - Initiating graceful shutdown
myblink  | 2026-02-15 13:52:51 - __main__ - INFO - Media manager stopped
myblink  | 2026-02-15 13:52:51 - web_server - INFO - Stopping web server
myblink  | 2026-02-15 13:52:51 - __main__ - INFO - Shutdown complete
myblink  | 2026-02-15 13:52:51 - __main__ - INFO - Stopped periodic media check
myblink  | 2026-02-15 13:52:51 - __main__ - INFO - Application terminated
myblink exited with code 0
 Container myblink  Stopped
@austinc3030 ➜ /workspaces/myblink (main) $ 



line 380, in request_videos
myblink  |     return await http_get(blink, url)
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/api.py", line 674, in http_get
myblink  |     return await blink.auth.query(
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/auth.py", line 271, in query
myblink  |     response = await self.session.get(
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/aiohttp/client.py", line 428, in _request
myblink  |     raise RuntimeError("Session is closed")
myblink  | RuntimeError: Session is closed
myblink  | 2026-02-15 13:44:53 - __main__ - ERROR - Failed to download thumbnail: Session is closed
myblink  | Traceback (most recent call last):
myblink  |   File "/app/modules/media_manager.py", line 313, in download_thumbnail
myblink  |     response = await camera.get_thumbnail()
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/camera.py", line 267, in get_thumbnail
myblink  |     return await api.http_get(
myblink  |            ^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/api.py", line 674, in http_get
myblink  |     return await blink.auth.query(
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/auth.py", line 271, in query
myblink  |     response = await self.session.get(
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/aiohttp/client.py", line 428, in _request
myblink  |     raise RuntimeError("Session is closed")
myblink  | RuntimeError: Session is closed
myblink  | 2026-02-15 13:44:53 - blinkpy.blinkpy - INFO - Retrieving videos since 2026-02-15T18:39:53+0000
myblink  | 2026-02-15 13:44:53 - __main__ - ERROR - Failed to download clips for Front Door Interior: Session is closed
myblink  | Traceback (most recent call last):
myblink  |   File "/app/modules/media_manager.py", line 446, in _download_new_clips
myblink  |     clips_metadata = await self.blink_handler.blink.get_videos_metadata(
myblink  |                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/blinkpy.py", line 414, in get_videos_metadata
myblink  |     response = await api.request_videos(self, time=since_epochs, page=page)
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/api.py", line 380, in request_videos
myblink  |     return await http_get(blink, url)
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/api.py", line 674, in http_get
myblink  |     return await blink.auth.query(
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/auth.py", line 271, in query
myblink  |     response = await self.session.get(
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/aiohttp/client.py", line 428, in _request
myblink  |     raise RuntimeError("Session is closed")
myblink  | RuntimeError: Session is closed
myblink  | 2026-02-15 13:44:53 - __main__ - ERROR - Failed to download thumbnail: Session is closed
myblink  | Traceback (most recent call last):
myblink  |   File "/app/modules/media_manager.py", line 313, in download_thumbnail
myblink  |     response = await camera.get_thumbnail()
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/camera.py", line 267, in get_thumbnail
myblink  |     return await api.http_get(
myblink  |            ^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/api.py", line 674, in http_get
myblink  |     return await blink.auth.query(
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/auth.py", line 271, in query
myblink  |     response = await self.session.get(
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/aiohttp/client.py", line 428, in _request
myblink  |     raise RuntimeError("Session is closed")
myblink  | RuntimeError: Session is closed
myblink  | 2026-02-15 13:44:53 - blinkpy.blinkpy - INFO - Retrieving videos since 2026-02-15T18:39:53+0000
myblink  | 2026-02-15 13:44:53 - __main__ - ERROR - Failed to download clips for Front Door: Session is closed
myblink  | Traceback (most recent call last):
myblink  |   File "/app/modules/media_manager.py", line 446, in _download_new_clips
myblink  |     clips_metadata = await self.blink_handler.blink.get_videos_metadata(
myblink  |                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/blinkpy.py", line 414, in get_videos_metadata
myblink  |     response = await api.request_videos(self, time=since_epochs, page=page)
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/api.py", line 380, in request_videos
myblink  |     return await http_get(blink, url)
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/api.py", line 674, in http_get
myblink  |     return await blink.auth.query(
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/auth.py", line 271, in query
myblink  |     response = await self.session.get(
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/aiohttp/client.py", line 428, in _request
myblink  |     raise RuntimeError("Session is closed")
myblink  | RuntimeError: Session is closed
myblink  | 2026-02-15 13:44:53 - __main__ - ERROR - Failed to download thumbnail: Session is closed
myblink  | Traceback (most recent call last):
myblink  |   File "/app/modules/media_manager.py", line 313, in download_thumbnail
myblink  |     response = await camera.get_thumbnail()
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/camera.py", line 267, in get_thumbnail
myblink  |     return await api.http_get(
myblink  |            ^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/api.py", line 674, in http_get
myblink  |     return await blink.auth.query(
myblink  |            ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/blinkpy/auth.py", line 271, in query
myblink  |     response = await self.session.get(
myblink  |                ^^^^^^^^^^^^^^^^^^^^^^^
myblink  |   File "/usr/local/lib/python3.12/site-packages/aiohttp/client.py", line 428, in _request
myblink  |     raise RuntimeError("Session is closed")
myblink  | RuntimeError: Session is closed


w Enable Watch