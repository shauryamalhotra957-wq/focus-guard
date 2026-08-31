# Security policy

Focus Guard observes camera frames locally and may control desktop notifications.

- Keep webcam frames, detections, and settings local; do not add uploads or telemetry without explicit consent.
- Do not commit model weights, captured frames, credentials, or personal logs.
- Treat model files and configuration as untrusted until verified.
- Preserve the safe default: no camera output or alert action should occur before the user arms the app.
- Review any new global hotkey or process-control behavior for accidental activation.

Report privacy leaks, unsafe process execution, or bypasses of the disarmed state privately to the repository owner with sanitized reproduction steps.
