#!/usr/bin/env python
import base64
import os
import subprocess

import aetherterm.agentserver as aetherterm
from aetherterm.agentserver.escapes import image
from aetherterm.agentserver.utils import ansi_colors

print(ansi_colors.white + "Welcome to the aetherterm help." + ansi_colors.reset)
path = os.getenv("AETHERTERM_PATH")
if path:
    path = os.path.join(path, "../static/images/favicon.png")

if path and os.path.exists(path):
    with image("image/png"):
        with open(path, "rb") as i:
            print(base64.b64encode(i.read()).decode("ascii"))
print(
    """
AetherTerm is a xterm compliant terminal built with python and javascript.

{title}Terminal functionalities:{reset}
  {strong}[ScrollLock]            : {reset}Lock the scrolling to the current position. Press again to release.
  {strong}[Ctrl] + [c] <<hold>>   : {reset}Cut the output when [Ctrl] + [c] is not enough.
  {strong}[Ctrl] + [Shift] + [Up] : {reset}Trigger visual selection mode. Hitting [Enter] inserts the selection in the prompt.
  {strong}[Alt] + [a]             : {reset}Set an alarm which sends a notification when a modification is detected. (Ring on regexp match with [Shift])
  {strong}[Alt] + [s]             : {reset}Open theme selection prompt. Use [Alt] + [Shift] + [s] to refresh current theme.
  {strong}[Alt] + [e]             : {reset}List open user sessions. (Only available in secure mode)
  {strong}[Alt] + [o]             : {reset}Open new terminal (As a popup)
  {strong}[Alt] + [z]             : {reset}Escape: don't catch the next pressed key.
                            Useful for using native search for example. ([Alt] + [z] then [Ctrl] + [f]).
{title}AetherTerm programs:{reset}
  {strong}aether    : {reset}Alias for {strong}aetherterm{reset} executable. Takes a comand in parameter or launch an aetherterm server for one shot use (if outside aetherterm).
  {strong}aether cat     : {reset}A wrapper around cat allowing to display images as <img> instead of binary.
  {strong}aether open    : {reset}Open a new terminal at specified location.
  {strong}aether session : {reset}Open or rattach an aetherterm session. Multiplexing is supported.
  {strong}aether colors  : {reset}Test the terminal colors (16, 256 and 16777216 colors)
  {strong}aether html    : {reset}Output in html standard input.

  For more aetherterm programs check out: https://github.com/paradoxxxzero/aetherterm-demos
{title}Styling AetherTerm:{reset}
  To style aetherterm in sass, you need to have the libsass python library installed.

  Theming is done by overriding the default sass files located in {code}{main}{reset} in your theme directory.
  This directory can include images and custom fonts.
  Please take a look at official themes here:  https://github.com/paradoxxxzero/aetherterm-themes
  and submit your best themes as pull request!

  \x1b[{rcol}G\x1b[3m{dark}aetherterm @ 2025 Mounier Florian{reset}\
""".format(
        title=ansi_colors.light_blue,
        dark=ansi_colors.light_black,
        strong=ansi_colors.white,
        code=ansi_colors.light_yellow,
        reset=ansi_colors.reset,
        rcol=int(subprocess.check_output(["stty", "size"]).split()[1]) - 31,
        main=os.path.normpath(
            os.path.join(os.path.abspath(os.path.dirname(aetherterm.__file__)), "sass")
        ),
    )
)
