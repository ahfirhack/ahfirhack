# Epic History Kids — Meta AI consistency contract

Generate three vertical historical videos for one continuous 30-second episode.
Every video is exactly ten seconds and uses the permanent Milo character lock.
The complete permanent character, style, continuity, and negative prompt is
injected into every video request. Scene 1 is generated directly from that
prompt. Scene 2 starts from scene 1's final frame, and scene 3 starts from scene
2's final frame. Keep identity, wardrobe, setting, lighting, camera direction,
and motion continuous. Do not add captions, dialogue, logos, black frames,
fades, or embedded music; narration is added afterward.

The automation-specific complete prompts are produced inside each episode's
`meta_ai_jobs/channel_3/<episode>/meta_prompts.txt` file.
