# Broken storyboard (on purpose)

`storyboard.json` has six common mistakes. `render_video.py --check` lists all of them at once and renders nothing. The exact output is in `expected-problems.txt`.

| Problem | Fix |
| --- | --- |
| Title is 83 characters | Keep a title to one idea: “Analytics your team will actually read.” |
| 12 words in 3 seconds | Give the title scene 5 seconds, or cut words |
| 19 words in 4 seconds | Split into two statements, or give it 7.5 seconds |
| `dashboard.png` does not exist | Put the screenshot next to the storyboard, at least 800×400 |
| Features has one item | Use 2–4 items |
| `button` is not a cta field | Use `url` for the address and `note` for the small line |
