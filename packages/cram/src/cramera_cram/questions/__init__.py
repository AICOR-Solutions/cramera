"""
The question engine: queries in krrood's entity query language about a live CRAM world
(:mod:`~cramera_cram.questions.live`) or a recorded scene
(:mod:`~cramera_cram.questions.scenes`), the ready-made questions, the plain-language
matching and the graph views.

The questions plugin of the viewer imports nothing of krrood; its routes hand their
requests to :class:`~cramera_cram.questions.scenes.RecordedSceneQuestions` and answer
with the protocol documents it returns.
"""
