"""ADK supervisor for Martini Shot (plan B-1, spec §5).

Scaffold: Post Supervisor persona + tool registry + autonomy toggle
(propose-only by default). Act-class tools (retry, stop, quarantine)
require explicit POST_COMMAND_AUTONOMY=act; in propose-only mode they
surface as proposals, never direct mutations (C-4.3 audit trail).
"""
