# Contributing

Install the Python requirements and run the tests:

~~~bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
~~~

Use synthetic frames and preview-only mode for detector work. Preserve the disarmed startup state, F8 emergency-neutral path, and one-alert-per-episode behavior. Add tests for state transitions and configuration changes.

Never commit webcam captures, model weights, or personal activity logs.
