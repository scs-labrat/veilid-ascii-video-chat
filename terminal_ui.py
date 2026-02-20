"""Curses-based terminal UI for ASCII video chat.

Layout
------
 ┌──────────────────────────────┬───────────────┐
 │        REMOTE VIDEO          │     CHAT      │
 │                              │               │
 │                              │ [12:34] You:  │
 │                              │   hello       │
 ├──────────────────────────────┤               │
 │        LOCAL PREVIEW         │               │
 │                              │               │
 ├──────────────────────────────┴───────────────┤
 │ ■ Connected | Room: VLD0:abc…                │
 ├──────────────────────────────────────────────┤
 │ > _                                          │
 └──────────────────────────────────────────────┘
"""

import curses
import sys
import textwrap


class TerminalUI:
    MIN_WIDTH = 60
    MIN_HEIGHT = 12

    def __init__(self, stdscr, *, color=True, show_local=True):
        self.stdscr = stdscr
        self.color_enabled = color
        self.show_local = show_local
        self.running = True

        # Frame buffers
        self.remote_frame = None
        self.remote_colors = None
        self.local_frame = None
        self.local_colors = None

        # Chat
        self.chat_lines: list[str] = []

        # Input
        self.input_buffer = ""
        self.cursor_pos = 0

        # Status
        self.status_text = "Starting..."

        # Curses setup
        curses.curs_set(1)
        stdscr.nodelay(True)
        stdscr.timeout(33)  # ~30 fps
        curses.start_color()
        curses.use_default_colors()

        self._setup_colors()
        self._calc_layout()

    # ------------------------------------------------------------------
    # Colour initialisation
    # ------------------------------------------------------------------
    def _setup_colors(self):
        if not self.color_enabled:
            return
        try:
            if curses.COLORS < 256:
                self.color_enabled = False
                return
            # Initialise pairs 1-255 mapping fg colour i → pair i
            for i in range(1, min(256, curses.COLOR_PAIRS)):
                try:
                    curses.init_pair(i, i, -1)
                except curses.error:
                    pass
        except Exception:
            self.color_enabled = False

    # ------------------------------------------------------------------
    # Layout calculation
    # ------------------------------------------------------------------
    def _calc_layout(self):
        h, w = self.stdscr.getmaxyx()
        self.term_h = h
        self.term_w = w

        # Chat panel width (right side)
        self.chat_w = max(22, w // 4)
        self.video_w = w - self.chat_w - 1  # 1 col for divider

        # Vertical: status (1) + input (1) at bottom
        self.video_h = h - 2

        if self.show_local:
            self.remote_h = max(1, (self.video_h * 2) // 3)
            self.local_h = self.video_h - self.remote_h
        else:
            self.remote_h = self.video_h
            self.local_h = 0

        self.status_y = h - 2
        self.input_y = h - 1

    # ------------------------------------------------------------------
    # Public setters
    # ------------------------------------------------------------------
    def set_remote_frame(self, lines, colors):
        self.remote_frame = lines
        self.remote_colors = colors

    def set_local_frame(self, lines, colors):
        self.local_frame = lines
        self.local_colors = colors

    def add_chat(self, formatted_msg: str):
        # Word-wrap to chat panel width
        wrapped = textwrap.wrap(formatted_msg, width=self.chat_w - 1)
        self.chat_lines.extend(wrapped if wrapped else [formatted_msg])

    def set_status(self, text: str):
        self.status_text = text

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def render(self):
        try:
            self.stdscr.erase()
            self._calc_layout()

            if self.term_w < self.MIN_WIDTH or self.term_h < self.MIN_HEIGHT:
                self._draw_too_small()
            else:
                self._draw_video_panel(
                    self.remote_frame, self.remote_colors,
                    0, 0, self.remote_h, self.video_w, "REMOTE",
                )
                if self.show_local and self.local_h > 0:
                    self._draw_video_panel(
                        self.local_frame, self.local_colors,
                        self.remote_h, 0, self.local_h, self.video_w, "LOCAL",
                    )
                self._draw_divider()
                self._draw_chat()
                self._draw_status()
                self._draw_input()

            self.stdscr.refresh()
        except curses.error:
            pass

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    def _draw_too_small(self):
        msg = "Terminal too small"
        y = self.term_h // 2
        x = max(0, (self.term_w - len(msg)) // 2)
        try:
            self.stdscr.addstr(y, x, msg, curses.A_BOLD)
        except curses.error:
            pass

    def _draw_video_panel(self, lines, colors, y_off, x_off, height, width, label):
        # Label
        try:
            self.stdscr.addstr(
                y_off, x_off, f" {label} "[:width], curses.A_REVERSE
            )
        except curses.error:
            pass

        if lines is None:
            cy = y_off + height // 2
            msg = "Waiting for video..."
            cx = x_off + max(0, (width - len(msg)) // 2)
            try:
                self.stdscr.addstr(cy, cx, msg[:width], curses.A_DIM)
            except curses.error:
                pass
            return

        for row_i in range(min(len(lines), height)):
            line = lines[row_i]
            row_colors = (
                colors[row_i]
                if colors and row_i < len(colors)
                else None
            )
            y = y_off + row_i
            if y >= self.term_h - 2:
                break

            for col_i in range(min(len(line), width)):
                x = x_off + col_i
                ch = line[col_i]
                try:
                    if (
                        self.color_enabled
                        and row_colors
                        and col_i < len(row_colors)
                    ):
                        pair = row_colors[col_i]
                        if 0 < pair < curses.COLOR_PAIRS:
                            self.stdscr.addch(
                                y, x, ch, curses.color_pair(pair)
                            )
                        else:
                            self.stdscr.addch(y, x, ch)
                    else:
                        self.stdscr.addch(y, x, ch)
                except curses.error:
                    pass

    def _draw_divider(self):
        x = self.video_w
        for y in range(self.video_h):
            try:
                self.stdscr.addch(y, x, curses.ACS_VLINE, curses.A_DIM)
            except curses.error:
                pass

    def _draw_chat(self):
        x_off = self.video_w + 1
        # Header
        try:
            self.stdscr.addstr(0, x_off, " CHAT "[:self.chat_w], curses.A_REVERSE)
        except curses.error:
            pass

        visible_rows = self.video_h - 1  # minus header row
        visible = self.chat_lines[-visible_rows:] if self.chat_lines else []
        for i, line in enumerate(visible):
            y = 1 + i
            if y >= self.video_h:
                break
            try:
                self.stdscr.addnstr(y, x_off, line, self.chat_w - 1)
            except curses.error:
                pass

    def _draw_status(self):
        bar = f" {self.status_text} "
        try:
            self.stdscr.addnstr(
                self.status_y, 0,
                bar.ljust(self.term_w),
                self.term_w - 1,
                curses.A_REVERSE,
            )
        except curses.error:
            pass

    def _draw_input(self):
        prompt = "> "
        display = prompt + self.input_buffer
        try:
            self.stdscr.addnstr(self.input_y, 0, display, self.term_w - 1)
            cx = len(prompt) + self.cursor_pos
            if cx < self.term_w:
                self.stdscr.move(self.input_y, cx)
        except curses.error:
            pass

    # ------------------------------------------------------------------
    # Input handling  (returns a completed message string or None)
    # ------------------------------------------------------------------
    def handle_input(self) -> str | None:
        try:
            ch = self.stdscr.getch()
        except curses.error:
            return None

        if ch == -1:
            return None

        # Enter
        if ch in (10, 13, curses.KEY_ENTER):
            msg = self.input_buffer.strip()
            self.input_buffer = ""
            self.cursor_pos = 0
            return msg if msg else None

        # Escape – clear input
        if ch == 27:
            self.input_buffer = ""
            self.cursor_pos = 0
            return None

        # Backspace
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if self.cursor_pos > 0:
                self.input_buffer = (
                    self.input_buffer[: self.cursor_pos - 1]
                    + self.input_buffer[self.cursor_pos :]
                )
                self.cursor_pos -= 1
            return None

        # Delete
        if ch == curses.KEY_DC:
            if self.cursor_pos < len(self.input_buffer):
                self.input_buffer = (
                    self.input_buffer[: self.cursor_pos]
                    + self.input_buffer[self.cursor_pos + 1 :]
                )
            return None

        # Arrow keys
        if ch == curses.KEY_LEFT:
            self.cursor_pos = max(0, self.cursor_pos - 1)
            return None
        if ch == curses.KEY_RIGHT:
            self.cursor_pos = min(len(self.input_buffer), self.cursor_pos + 1)
            return None
        if ch == curses.KEY_HOME:
            self.cursor_pos = 0
            return None
        if ch == curses.KEY_END:
            self.cursor_pos = len(self.input_buffer)
            return None

        # Terminal resize
        if ch == curses.KEY_RESIZE:
            self._calc_layout()
            return None

        # Printable ASCII + common extended
        if 32 <= ch <= 126:
            self.input_buffer = (
                self.input_buffer[: self.cursor_pos]
                + chr(ch)
                + self.input_buffer[self.cursor_pos :]
            )
            self.cursor_pos += 1

        return None
