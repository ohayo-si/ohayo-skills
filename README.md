# Ohayo skills

Free agent skills for Claude Code and Codex from [Ohayo](https://ohayo.si). Each one ships with scripts that check their own output and automated tests, so your agent can tell you when something is wrong instead of guessing.

| Skill | What your agent can do with it | License |
| --- | --- | --- |
| [Launch Video Kit Lite](launch-video-kit-lite/) | Turn your screenshots into a 16:9 launch video. Text, contrast, reading speed and images are checked before rendering; the MP4 is validated after. Python, Pillow and ffmpeg. | MIT |

## Install a skill

```bash
git clone --depth 1 https://github.com/ohayo-si/ohayo-skills
mkdir -p ~/.claude/skills            # Codex: ~/.codex/skills
cp -R ohayo-skills/launch-video-kit-lite ~/.claude/skills/
```

Start a new session and ask your agent, for example: “Make a 30-second launch video for my app from these screenshots.”

## More

Full versions with more styles, formats and features are at [ohayo.si/skills](https://ohayo.si/skills/). Need a skill for your own workflow? [Request one](https://ohayo.si/custom/).
