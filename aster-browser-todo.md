# Aster Browser — Full Build Todo List

> Complete checklist for building Aster from scratch, including all existing working features and all suggested improvements. Phases are ordered by dependency and impact.

---

## ⚠️ Agent Directives — Read Before Starting

> **These rules apply for the entire duration of the build. Do not skip or override them.**

- **Do NOT stop until every single checkbox in this document is ticked.** Work through each phase in order, top to bottom. If a task is blocked by a dependency, resolve the dependency first and then return. Stopping mid-checklist is not acceptable under any circumstance.
- **UI quality is non-negotiable.** Every visible surface — sidebar, topbar, address bar, panels, popovers, tooltips, badges, scrollbars, dividers, animations — must look polished, intentional, and premium. There is no such thing as a "placeholder UI" that ships. If something is on screen, it must be beautiful. Refer to the UI Quality Standards below before touching any rendering code.
- **Complete each phase fully before moving to the next.** Do not leave partial implementations behind. Every checkbox must represent a genuinely working, tested, visually correct feature — not just scaffolding or a stub.
- **After the final phase, do not stop — proceed immediately to Phase 22 (QA & Refinement).** That phase is the last gate before the build is considered done.

---

## 🎨 UI Quality Standards — Applies to Every Phase

> Every piece of UI built in this project must meet all of the following standards. These are not optional polish — they are requirements.

- **Spacing & rhythm** — All padding, margins, and gaps must follow a consistent 4px base grid. Nothing is placed arbitrarily. Every element has breathing room.
- **Typography** — Use a single high-quality system font stack (e.g. `Segoe UI Variable` on Windows, fallback to `Segoe UI`). Font sizes must follow a clear scale (12 / 13 / 14 / 16 / 20 / 24px). Line heights must be set explicitly. No text should feel cramped or float without a clear baseline.
- **Colour discipline** — Every colour used in the UI must come from the defined palette constants (dark theme or light theme). No magic hex literals anywhere in rendering code. Hover, active, focused, and disabled states must each have a distinct, visually legible colour.
- **Micro-interactions & hover states** — Every interactive element (buttons, tab rows, folder rows, icons, address bar, scrollbar) must have a visible hover state with a smooth transition (100–150ms ease). Click/active states must have a distinct pressed appearance (slight scale or brightness change).
- **Animations must feel natural** — All show/hide transitions (sidebar, panels, popovers, find bar) must use an easing curve (ease-out for appearing, ease-in for disappearing). Duration should be 150–250ms. Nothing should snap or teleport into view.
- **Icons must be crisp and consistent** — All icons must be rendered at the correct DPI-aware pixel size. Use a single consistent icon style throughout (either all outline or all filled — do not mix). All icons must be pixel-aligned at 100% and 125% and 150% DPI.
- **Rounded corners everywhere** — Buttons, pills, panels, popovers, tab rows, and badges all use consistent border radii (4px for small elements, 8px for panels, 12px for large cards/modals). No sharp-cornered UI surfaces.
- **Depth & layering** — Use subtle drop shadows (1–3px blur, low opacity) to communicate which elements are floating (popovers, peek panels, command palette). The main window surface must feel flat; floating elements must feel elevated.
- **Empty states** — Every panel that can be empty (bookmarks, downloads, history, containers) must have a well-designed empty state: an illustrative icon, a short headline, and a brief instructional subtitle. No blank white boxes.
- **Loading states** — Every async operation (navigation, download start, filter list update, session restore) must have a visible loading indicator. No operation should feel frozen or unresponsive.
- **Error states** — Every operation that can fail must have a designed error state shown in the UI. Errors must be human-readable, not raw error codes. Include a recovery action (e.g. "Retry", "Open Settings") wherever possible.
- **Scrollbars** — All scrollable areas (tab list, bookmarks panel, downloads panel, command palette results) must have a minimal, styled scrollbar — thin (6px), rounded, auto-hiding after 1.5s of inactivity, visible on hover of the scroll container.
- **No visual regressions** — Any change to rendering code must be verified not to break the appearance of other UI regions. Run a visual check of the full window after every significant rendering change.

---

## Phase 1 — Foundation & Core Shell

> Get a window on screen with a functional WebView2 host and basic rendering pipeline.

### Win32 Window & Rendering Infrastructure

- [ ] **Create the Win32 application entry point** — Register a window class, create the main `HWND`, and run the message loop. Handle `WM_CREATE`, `WM_DESTROY`, `WM_CLOSE`, and `WM_QUIT` correctly.
- [ ] **Set up double-buffered GDI rendering** — Create an off-screen `HDC` and `HBITMAP` the same size as the client rect. All painting goes to the back buffer; `WM_PAINT` only does a single `BitBlt` to eliminate flicker. On `WM_SIZE`, destroy and recreate the back buffer at the new dimensions.
- [ ] **Create a reusable font registry** — Load and cache `HFONT` handles for every typeface/size combo used in the UI (sidebar labels, address bar text, tooltip text, etc.). Implement `Drop` on each font wrapper so `DeleteObject` is called automatically.
- [ ] **Create a reusable brush registry** — Same pattern for `HBRUSH` handles (background fills, hover fills, active fills, separator colours). Implement `Drop` for each.
- [ ] **Create a reusable bitmap registry** — Cache `HBITMAP` handles for icons and decorative bitmaps. Implement `Drop`.
- [ ] **Implement a `refresh()` helper** — Calls `InvalidateRect` to schedule a repaint. Initially invalidate the whole window; this will be made selective later in Phase 7.
- [ ] **Implement selective region invalidation** — Track named dirty regions (sidebar, address bar, content area, topbar). `refresh_sidebar()`, `refresh_topbar()`, etc. each invalidate only their own `RECT` so unrelated areas are never repainted.
- [ ] **Procedural animated background** — Render a subtle generative pattern (gradient mesh, noise, or geometric) in the background layer of the shell chrome. Animate it on a timer so it shifts slowly over time. The pattern must only repaint when its own timer fires, not on every UI event.
- [ ] **Dark theme colour palette** — Define all shell colours as named constants: background, surface, surface-raised, border, text-primary, text-secondary, accent, hover, active. All GDI drawing references these constants — no hard-coded colour literals elsewhere.
- [ ] **Light theme colour palette** — Define a parallel set of named constants for a light theme. Add a runtime theme toggle that swaps the active palette and triggers a full shell repaint.
- [ ] **DPI awareness** — Call `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)`. On `WM_DPICHANGED`, rescale all layout constants and recreate fonts at the new DPI.

---

## Phase 2 — WebView2 Integration

> Embed a fully functional Chromium webview inside the shell window.

### WebView2 Lifecycle

- [ ] **Initialize WebView2 environment** — Call `CreateCoreWebView2EnvironmentWithOptions` with a dedicated user data folder (e.g. `%APPDATA%\Aster\WebView2`). Handle the async callback correctly. If initialization fails, show a user-visible error dialog instead of crashing.
- [ ] **Create the WebView2 controller and host** — Call `CreateCoreWebView2Controller` once the environment is ready. Position the controller to fill the content area (below topbar, right of sidebar).
- [ ] **Implement smart WebView2 child `HWND` detection** — After creation, enumerate child windows of the main `HWND`, diff against the pre-creation list, and store the new child `HWND`. Use this handle for hit-testing, focus management, and resize coordination.
- [ ] **Navigate to a URL** — Expose a `navigate(url: &str)` method that calls `Navigate` or `NavigateToString` on the active WebView2 controller. Normalise bare hostnames into `https://` URLs automatically.
- [ ] **Handle navigation events** — Subscribe to `NavigationStarting`, `NavigationCompleted`, `SourceChanged`, `DocumentTitleChanged`, and `FaviconChanged`. Update address bar text, tab title, loading spinner, and favicon on each.
- [ ] **Handle new window requests** — Subscribe to `NewWindowRequested`. Open the target URL in a new tab in the sidebar instead of letting WebView2 spawn an OS window.
- [ ] **Handle fullscreen requests** — Subscribe to `ContainsFullScreenElementChanged`. When a page goes fullscreen (e.g. a video), hide the topbar and sidebar, resize the WebView2 to fill the whole window. Restore on exit. Also toggle fullscreen via `F11`.
- [ ] **Per-tab site theme switching** — Call `put_PreferredColorScheme` on the WebView2 settings per tab. Expose three options: Auto (follow OS), Force Dark, Force Light. Store the preference per tab in state.
- [ ] **Implement lazy tab loading on startup** — When restoring a saved session, create tab entries in the sidebar with their stored title/URL/favicon but do not create a WebView2 controller until the tab is first activated. This dramatically reduces startup memory.
- [ ] **Error recovery for WebView2 initialization failure** — If `CreateCoreWebView2EnvironmentWithOptions` returns an error (e.g. runtime not installed), show a modal dialog with a link to the WebView2 Evergreen installer and gracefully exit.

---

## Phase 3 — Vertical Tab Sidebar

> Full sidebar with tab management, animated show/hide, and three display modes.

### Tab Data Model

- [ ] **Define the `Tab` struct** — Fields: `id` (unique u64), `title` (String), `url` (String), `favicon` (Option<HBITMAP>), `is_pinned` (bool), `is_sleeping` (bool), `is_loading` (bool), `scroll_offset` (i32), `webview_controller` (Option<...>), `history` (Vec<HistoryEntry>), `history_index` (usize), `site_theme` (ThemeMode).
- [ ] **Define the `Folder` struct** — Fields: `id` (unique u64), `name` (String), `children` (Vec<TabOrFolder>), `is_collapsed` (bool), `is_pinned` (bool).
- [ ] **Define `TabOrFolder` enum** — Wraps either a `Tab` or `Folder`, allowing arbitrary nesting depth.
- [ ] **Define the `AppState` struct** — Holds the active workspace index, the list of workspaces, global UI state (sidebar mode, active tab id, drag state, etc.).

### Sidebar Rendering

- [ ] **Render the tab list** — For each tab in the active workspace's root, draw a row showing favicon (16×16), title (truncated with ellipsis), and a close button. Highlight the active tab with the accent background.
- [ ] **Render nested folders** — Indent child tabs by one level. Draw a folder icon + name row. Render a collapse/expand chevron on hover. Support arbitrary nesting depth.
- [ ] **Render pinned tab indicator** — Show a pin icon badge on pinned tab rows. Pinned tabs appear at the top of the list above a separator line.
- [ ] **Render sleeping tab indicator** — Show a moon/sleep icon badge on sleeping tabs. Sleeping tabs have dimmed title text.
- [ ] **Render loading spinner** — For tabs currently navigating, replace the favicon with an animated spinner (rotate a segmented arc on a 60ms timer).
- [ ] **Sidebar scroll** — If the tab list exceeds the sidebar height, make it scrollable. Handle `WM_MOUSEWHEEL` over the sidebar to scroll the list. Draw a minimal scrollbar indicator on the right edge of the sidebar.
- [ ] **Three sidebar display modes** — `Hidden`: sidebar is not rendered, content fills full width. `Overlay`: sidebar floats over the content, content does not shrink. `Pushed`: sidebar pushes content to the right, reducing its width. Store mode in config and persist.
- [ ] **Animated sidebar show/hide** — On toggle, animate the sidebar width from 0 to its target (or vice versa) over ~200ms using an easing curve. Use a `WM_TIMER` to drive the animation frames. The sidebar toggle button appears in the topbar.
- [ ] **Tab hover state** — Track which tab row the mouse is over. On `WM_MOUSEMOVE`, if the hovered tab changes, repaint only the sidebar region. Show the close button only on hover.
- [ ] **Tab click to activate** — On `WM_LBUTTONDOWN` in the sidebar, hit-test against tab rows. Activate the clicked tab (swap WebView2 controllers, update address bar).
- [ ] **Close button click** — If the close button on a tab row is clicked, close that tab. If it is pinned, instead put it to sleep (preserve the WebView2 controller state) rather than destroying it.
- [ ] **New tab button** — Render a `+` button at the bottom of the sidebar (or top). On click, create a new tab, navigate to a blank page or configured homepage, and activate it.

### Drag-and-Drop Reordering

- [ ] **Begin drag on mouse-down + move threshold** — When the user presses and holds on a tab row then moves the mouse more than ~4px, enter drag mode. Record the dragged item id and the initial cursor offset within the row.
- [ ] **Ghost preview rendering** — While dragging, render a semi-transparent copy of the dragged tab row at the cursor position as a ghost. Render a horizontal insertion indicator line between other tabs showing where the drop will land.
- [ ] **Virtual drag state** — Do not mutate the actual tab list while dragging. Maintain a separate virtual ordering that the renderer uses. Only commit the reorder on mouse-up.
- [ ] **Drop into a folder** — If the ghost is held over a folder row for >400ms, expand the folder automatically and allow dropping inside it.
- [ ] **Drop to create a folder** — If the ghost is held directly over another tab (not a folder) for >600ms, wrap both tabs in a new unnamed folder. Prompt the user to name it.
- [ ] **Cancel drag on Escape** — Pressing `Escape` during a drag restores the original order and cancels the operation.

---

## Phase 4 — Topbar & Address Bar

> Navigation controls, address/search pill, and status indicators.

- [ ] **Render the topbar strip** — A fixed-height bar at the top of the window. Contains (left-to-right): sidebar toggle, back, forward, reload/stop, address pill, zoom indicator, reader mode icon, shields icon, downloads icon.
- [ ] **Back button** — On click, call `GoBack` on the active WebView2. Disable (grey out) when `CanGoBack` is false.
- [ ] **Forward button** — On click, call `GoForward`. Disable when `CanGoForward` is false.
- [ ] **Reload / Stop button** — When loading: show an ✕ stop icon; on click call `Stop`. When idle: show a circular reload icon; on click call `Reload`. Toggle based on `NavigationStarting` / `NavigationCompleted` events.
- [ ] **Address pill rendering** — A rounded-rect input area showing the current URL or page title (toggle on click). On focus, select all text and switch to editable URL mode. On blur without commit, revert to display mode.
- [ ] **Address bar input handling** — Intercept `WM_CHAR`, `WM_KEYDOWN`. Support caret movement, selection, cut/copy/paste. On `Enter`, call `navigate()`. On `Escape`, blur without committing.
- [ ] **Frecency-powered command palette / autocomplete dropdown** — As the user types, score all visited URLs and open tabs by frecency (frequency × recency decay). Show the top 8 results in a dropdown below the address pill. Arrow keys navigate the list; `Enter` selects; `Escape` dismisses.
- [ ] **Search fallback** — If the typed text is not a valid URL, construct a search query URL using the configured default search engine (default: DuckDuckGo) and navigate to it.
- [ ] **Zoom indicator** — Show the current zoom percentage (e.g. `110%`) in the topbar when zoom ≠ 100%. Click to reset to 100%. `Ctrl++` / `Ctrl+-` adjust zoom via `put_ZoomFactor`. `Ctrl+0` resets.
- [ ] **Reader mode icon** — Show a paragraph/book icon in the topbar when the active page is detected as an article (check for `<article>` tag or sufficient `<p>` text density via a script injected after `NavigationCompleted`). On click, activate reader mode.
- [ ] **Back/forward context menus** — On right-click of the back or forward button, show a dropdown menu listing the tab's history stack. Clicking any entry navigates directly to that history position.

---

## Phase 5 — Workspaces (Spaces)

> Isolated browsing contexts with a visual switcher.

- [ ] **Define the `Workspace` struct** — Fields: `id` (u64), `name` (String), `color` (RGB), `icon` (Option<char> emoji or icon index), `tabs` (Vec<TabOrFolder>), `active_tab_id` (Option<u64>).
- [ ] **Workspace switcher UI** — Render a row of workspace chips (or a column, if sidebar is in vertical mode) along the bottom or top of the sidebar. Each chip shows the workspace icon/emoji and name.
- [ ] **Create a new workspace** — A `+` button in the switcher opens a creation dialog (name + color/emoji picker). Creates a new empty workspace and switches to it.
- [ ] **Switch workspace** — Clicking a workspace chip deactivates all WebView2 controllers for the current workspace (hide them), activates the controllers for the new workspace (show the active tab's controller), and updates all UI state.
- [ ] **Per-workspace tab list isolation** — Each workspace has its own completely independent tab list, folder tree, and active tab. Switching workspaces fully replaces the sidebar content.
- [ ] **Rename / delete workspace** — Right-click a workspace chip to show a context menu with Rename and Delete options. Deleting a workspace closes all its tabs (with a confirmation dialog if any are unsaved).
- [ ] **Workspace visual colour coding** — Each workspace has an accent colour used for its chip indicator and a subtle tint in the sidebar when that workspace is active.

---

## Phase 6 — Tab History & Session Persistence

### Per-Tab History

- [ ] **Define `HistoryEntry` struct** — Fields: `url` (String), `title` (String), `visited_at` (timestamp), `scroll_position` (i32).
- [ ] **Record navigation in per-tab history** — On `NavigationCompleted`, push a `HistoryEntry` onto the active tab's history Vec. Cap at 80 entries (configurable). Truncate forward history when a new navigation occurs (not back/forward).
- [ ] **Back/forward navigation updates history index** — On `GoBack`/`GoForward`, update `history_index` in the tab struct so the correct entry is highlighted in the context menu dropdown.

### Global Visited Sites (Frecency)

- [ ] **Maintain a global visited-sites store** — A `HashMap<String (origin), VisitedSite>` capped at 500 entries (configurable). `VisitedSite` holds visit count, last-visited timestamp, and page title.
- [ ] **Update on every navigation** — After each `NavigationCompleted`, upsert the visited-site record and recalculate frecency scores for autocomplete.
- [ ] **Frecency scoring algorithm** — Score = visit_count × decay_factor, where decay_factor = e^(–λ × days_since_last_visit). Tune λ so a site visited once a week scores higher than one visited 20 times a year ago.

### Closed Tabs

- [ ] **Closed tabs ring buffer** — Maintain a ring buffer of the last 100 closed tabs (configurable). Each entry stores title, URL, favicon, and closed timestamp.
- [ ] **Reopen closed tab** — `Ctrl+Shift+Z` reopens the most recently closed tab, creates a new `Tab` with its stored URL, and navigates to it. Preserve order in the ring buffer.
- [ ] **Recently Closed Tabs panel** — A panel (accessible from sidebar context menu or a topbar button) that lists all entries in the ring buffer: favicon + title + URL + time-ago label (e.g. "3 minutes ago"). Clicking any entry reopens it.

### State Persistence

- [ ] **Define the `.aster-state` file format** — TSV-based format. Sections delimited by header rows. Stores: workspaces (id, name, color, icon), tabs (workspace_id, id, title, url, is_pinned, is_sleeping, folder_id, history_index), folders (workspace_id, id, name, is_collapsed, is_pinned, parent_folder_id), closed tabs ring buffer, visited sites store, and UI config (sidebar mode, active workspace, sidebar width).
- [ ] **Save state on every meaningful change** — Debounce saves: schedule a 2-second delayed write on any state mutation; cancel and reschedule if another mutation arrives within the window. Write atomically (write to `.aster-state.tmp`, then rename).
- [ ] **Load state on startup** — Parse `.aster-state` at launch. Restore all workspaces, folders, and tab metadata. Do NOT create WebView2 controllers yet (lazy loading). Navigate the active tab of the active workspace immediately.
- [ ] **State file migration versioning** — Include a version field in the state file header. On load, if version < current, run a migration function to upgrade the format before parsing.

---

## Phase 7 — Bookmarks System

- [ ] **Define `Bookmark` and `BookmarkFolder` structs** — `Bookmark`: id, title, url, favicon, created_at, tags (Vec<String>). `BookmarkFolder`: id, name, children (Vec<BookmarkOrFolder>).
- [ ] **Persist bookmarks** — Store in a separate `bookmarks.tsv` file in the same format as the state file, or as a section within `.aster-state`.
- [ ] **Bookmark button in topbar** — A star icon in the topbar. Filled star = already bookmarked; outline = not bookmarked. On click: if not bookmarked, add current page to bookmarks (show a small popover to confirm/edit title and choose folder). If already bookmarked, show the same popover pre-filled for editing or deletion.
- [ ] **`Ctrl+D` shortcut** — Same as clicking the bookmark button.
- [ ] **Bookmarks panel** — A slide-in panel from the sidebar or a dedicated sidebar section. Shows the full bookmark tree with folders. Click to navigate to a bookmark. Right-click for Edit / Delete / Move-to-folder options.
- [ ] **Bookmark search** — A search field at the top of the bookmarks panel. Filters by title, URL, and tags in real time as the user types.
- [ ] **Add bookmark folder** — A `+ Folder` button in the bookmarks panel. Inline-edit the folder name.
- [ ] **Drag-and-drop bookmark reordering** — Same ghost-preview drag system as tab reordering but within the bookmarks panel.
- [ ] **Bookmark tags** — Allow each bookmark to have multiple free-form tags. A tag filter sidebar within the bookmarks panel lets users filter by tag.

---

## Phase 8 — Downloads Manager

- [ ] **Intercept downloads via WebView2** — Subscribe to `DownloadStarting` on the WebView2 controller. Instead of allowing the default browser download dialog, capture each download and create a `Download` entry in the app's download list.
- [ ] **Define `Download` struct** — Fields: id, url, filename, total_bytes, received_bytes, state (Pending / InProgress / Paused / Completed / Failed / Cancelled), started_at, completed_at, local_path.
- [ ] **Downloads panel UI** — A slide-in panel from the bottom-right of the window, triggered by `Ctrl+J` or a download icon in the topbar. Lists all downloads from the current session (and persisted history from prior sessions). Each row shows: filename, progress bar, received/total size, speed (bytes/sec), Pause / Resume / Cancel / Open-folder buttons.
- [ ] **Download progress updates** — On `BytesReceivedChanged` events from WebView2, update the `received_bytes` field and trigger a repaint of only the downloads panel.
- [ ] **Pause and resume** — Call `Pause()` and `Resume()` on the `ICoreWebView2DownloadOperation` object. Update button states accordingly.
- [ ] **Cancel and remove** — Call `Cancel()`. Remove the entry from the active list. Optionally delete the partial file.
- [ ] **Open containing folder** — Call `ShellExecute` with the download's directory path to open File Explorer at that location.
- [ ] **Downloads badge on topbar icon** — While any download is active, show an animated progress ring around the downloads icon. Show a green checkmark badge when a download completes.
- [ ] **Persist download history** — Save completed downloads to a `downloads.tsv` file so previous downloads are visible when the panel is reopened.

---

## Phase 9 — Find in Page

- [ ] **Find bar UI** — A compact bar that slides down from the top-right of the content area (not the topbar) on `Ctrl+F`. Contains: text input, match count label (e.g. `3 / 17`), Previous (↑) and Next (↓) buttons, and a close (✕) button.
- [ ] **Trigger search on input** — As the user types (debounced by ~100ms), call `ExecuteScriptAsync` to use the browser's built-in `window.find()` or inject a highlight script to mark all matches. Update match count.
- [ ] **Next / Previous match** — `Enter` and `Shift+Enter` (and the ↑/↓ buttons) advance/retreat through matches. Scroll the active match into view.
- [ ] **Dismiss find bar** — `Escape` hides the find bar and clears all highlights. Also clear on navigation.
- [ ] **Case-sensitivity toggle** — A small `Aa` button in the find bar to toggle case-sensitive search. Persist this preference.
- [ ] **Whole-word toggle** — A `W` button to restrict matches to whole words.

---

## Phase 10 — Reader Mode

- [ ] **Article detection heuristic** — After each `NavigationCompleted`, inject a content-detection script that checks for the presence of an `<article>` element, a `<main>` element, or a sufficient ratio of `<p>` text to total DOM node count. If the heuristic passes, activate the reader icon in the topbar.
- [ ] **Content extraction** — On reader mode activation, inject a JS script (based on Mozilla's Readability algorithm) that extracts article title, author, estimated read time, and body content as clean HTML.
- [ ] **Reader view rendering** — `NavigateToString` with a custom HTML template that applies reader mode styles: user-selected font (Serif / Sans / Mono), font size control, line height, max-content-width, and theme (Light / Sepia / Dark). Render the extracted content inside this template.
- [ ] **Reader mode controls** — A small floating toolbar in reader mode for: font family toggle, font size +/−, theme toggle (Light / Sepia / Dark), and an "Exit Reader" button.
- [ ] **Per-tab reader mode memory** — If a user activated reader mode on a tab, remember this preference so that revisiting the same origin (or same URL) auto-activates reader mode.

---

## Phase 11 — Built-in Content Blocking (Shields)

- [ ] **Register a `WebResourceRequested` filter** — Use `add_WebResourceRequested` on the WebView2 controller with a filter for all URLs (`*`) to intercept every outgoing request.
- [ ] **Load a filter list** — Bundle a compiled version of EasyList and EasyPrivacy (or a curated subset). Parse into a trie or Aho-Corasick automaton for fast matching at the domain/path level.
- [ ] **Block matching requests** — In the `WebResourceRequested` handler, if the request URL matches a filter rule, call `Response` with a dummy 200 OK and empty body (or cancel the request). Do not block first-party requests.
- [ ] **Shields icon in topbar** — Show a shield icon in the topbar. When the current page has had requests blocked, show a badge with the count of blocked requests. On click, open a Shields popover.
- [ ] **Shields popover** — Shows: total blocked count for this page, a toggle to disable shields for this site (stored in a per-site allowlist), and the top blocked domains listed.
- [ ] **Per-site allowlist** — Persist a set of origins for which shields are disabled. Check this allowlist in the `WebResourceRequested` handler before applying rules.
- [ ] **Filter list auto-update** — On startup (or weekly), fetch the latest filter list from its canonical URL, parse, and replace the compiled trie. Show update status in settings.
- [ ] **Cosmetic filtering (CSS injection)** — Beyond request blocking, inject per-domain CSS rules from the filter list to hide ad placeholder elements (element hiding rules like `##.ad-banner`).

---

## Phase 12 — Container Tabs

- [ ] **Define `Container` struct** — Fields: id (u64), name (String), color (RGB), icon (emoji). Built-in containers: Personal, Work, Shopping, Private. Users can create custom ones.
- [ ] **Per-container WebView2 user data folder** — Each container maps to a distinct WebView2 user-data directory (e.g. `%APPDATA%\Aster\Containers\work\`), giving fully isolated cookies, cache, local storage, and login sessions.
- [ ] **Assign a container to a tab** — When creating a tab, allow selection of a container from a small popover. Default: Personal. Store `container_id` on the `Tab` struct.
- [ ] **Container colour strip on tab rows** — Draw a 3px colour bar on the left edge of each tab row in the sidebar using the container's colour. This gives instant at-a-glance context.
- [ ] **Container indicator in address pill** — Show a small coloured dot and container name label in the address pill.
- [ ] **"Open in container" context menu** — When right-clicking a link, offer "Open in [container name]" options for each defined container.
- [ ] **Container management panel** — In settings, a Containers page where users can create, rename, recolour, and delete containers.

---

## Phase 13 — Split View

- [ ] **Trigger split view** — User selects two tabs in the sidebar (Ctrl+click to multi-select) and chooses "Split View" from a context menu, OR drags a tab onto another while holding `Alt`.
- [ ] **Split view layout engine** — Resize the content area to show two WebView2 controllers side by side (50/50 by default). Position each controller by setting its bounds on the `ICoreWebView2Controller`.
- [ ] **Draggable divider** — Render a thin vertical divider bar between the two panels. On `WM_LBUTTONDOWN` on the divider, enter a resize drag mode. On `WM_MOUSEMOVE`, update the split ratio. On `WM_LBUTTONUP`, commit.
- [ ] **Split view entry in sidebar** — Show a special combined row in the sidebar for the split pair: two stacked favicons + both titles. Clicking activates/focuses the split view.
- [ ] **Exit split view** — A button in the topbar (or sidebar row context menu) to exit split view. Both tabs return to the normal tab list independently.
- [ ] **Multi-split support** — Allow more than two panels (e.g. 3-column split). The split ratio is stored as a list of proportional weights.

---

## Phase 14 — Peek / Quick Preview

- [ ] **Detect Shift+click on links** — Inject a JS listener that intercepts click events where `event.shiftKey === true` and posts a message to the host via `window.chrome.webview.postMessage({type: 'peek', url: href})` instead of navigating.
- [ ] **Create a peek WebView2 controller** — On receiving a peek message, create a secondary (off-screen or floating) WebView2 controller and navigate it to the peeked URL.
- [ ] **Peek panel rendering** — Render the peek controller in a floating panel that overlays the main content. The panel has a fixed max-width and height, a close (✕) button, and an "Open in Tab" button.
- [ ] **Dismiss peek** — Pressing `Escape` or clicking outside the peek panel destroys the peek controller and hides the panel.
- [ ] **Open peek URL in tab** — Clicking "Open in Tab" converts the peek into a real tab: move the peek controller into the tab list, give it a proper tab entry, and close the panel.
- [ ] **Peek hover intent detection** — Optionally: on hovering a link for >500ms, show a micro-thumbnail preview (screenshot of the peek controller rendered off-screen) before the full peek opens.

---

## Phase 15 — Command Palette & Tab Search

- [ ] **Command palette trigger** — `Ctrl+K` or `Ctrl+Space` opens a full command palette overlay. The palette is a centered floating panel with a text input at the top and a scrollable results list below.
- [ ] **Open tabs section** — The top section of the palette shows all open tabs across all workspaces. Each result shows favicon, title, URL, and workspace name. Typing filters by title and URL.
- [ ] **History section** — Below open tabs, show frecency-ranked visited URLs matching the query.
- [ ] **Bookmarks section** — Show matching bookmarks.
- [ ] **Commands section** — Show browser commands matching the query: "New Tab", "New Workspace", "Toggle Shields", "Open Downloads", "Open Bookmarks", "Settings", etc.
- [ ] **Keyboard navigation** — Arrow keys move the selection. `Enter` activates. `Escape` closes. The palette never uses mouse as the primary interaction model.
- [ ] **Tab search shortcut** — `Ctrl+Shift+A` opens the palette pre-filtered to open tabs only.
- [ ] **Frecency ranking in palette** — Combine frequency of visits, recency, and string match quality (prefix match scores higher than substring) to rank results.

---

## Phase 16 — Session Save & Restore

- [ ] **Named session snapshots** — A "Sessions" panel (in settings or sidebar) allows the user to save the current entire state (all workspaces, tabs, folders) as a named snapshot. Snapshots are stored as separate `.aster-session-<name>.tsv` files.
- [ ] **Restore a session** — Opening a saved session replaces the current state with the snapshot's state. Offer an option to merge (add snapshot workspaces alongside existing ones) or replace entirely.
- [ ] **Auto-save session on crash / unexpected close** — Monitor for abnormal termination via a lock file or crash handler. On next startup, if a recovery file exists, offer to restore the previous session.
- [ ] **Session list UI** — Show session name, creation date, tab count, and workspace count. Buttons: Restore, Rename, Delete, Export-as-file.

---

## Phase 17 — Screenshot Tool

- [ ] **Full-page screenshot** — `Ctrl+Shift+S` opens a screenshot mode selector. "Full Page" calls `CapturePreview` on the WebView2 controller with `COREWEBVIEW2_CAPTURE_PREVIEW_IMAGE_FORMAT_PNG` and saves the result.
- [ ] **Region screenshot** — "Region" enters a crosshair selection mode. The user drags a rectangle over the window. The selection is captured by combining the WebView2 screenshot with Win32 GDI region clipping.
- [ ] **Visible area screenshot** — "Visible" captures only what is currently in the WebView2 viewport.
- [ ] **Post-capture actions** — After capture, show a small non-modal toast with options: Copy to Clipboard (`SetClipboardData` with `CF_DIB`), Save to File (show Save dialog), and Discard.
- [ ] **Annotation layer** — Optionally: after capture, open a minimal annotation overlay where the user can draw arrows, add text labels, and crop before saving.

---

## Phase 18 — Import from Other Browsers

- [ ] **Detect installed browsers** — Scan registry keys and common `%LOCALAPPDATA%` paths for Chrome, Firefox, Edge, Brave, and Opera installations. Show only detected browsers in the import wizard.
- [ ] **Import Chrome/Edge/Brave bookmarks** — Parse `Bookmarks` JSON file from the browser's user data directory. Map the tree structure to Aster's `BookmarkFolder` / `Bookmark` structs. Merge or replace based on user choice.
- [ ] **Import Firefox bookmarks** — Open `places.sqlite` (copy first to avoid lock conflicts) using a bundled SQLite reader. Query `moz_bookmarks` joined with `moz_places`. Map to Aster bookmarks.
- [ ] **Import history** — For Chrome/Edge/Brave, parse `History` SQLite file (`urls` table). For Firefox, query `moz_places` from `places.sqlite`. Import into Aster's visited-sites store and per-tab history as applicable.
- [ ] **Import UI wizard** — A multi-step import panel: Step 1 — select source browser. Step 2 — select what to import (checkboxes: Bookmarks, History). Step 3 — choose merge vs replace for each category. Step 4 — progress indicator and completion summary.

---

## Phase 19 — Configuration File

- [ ] **Create `%APPDATA%\Aster\config.toml`** — On first launch, write a default config file with all configurable values and inline comments documenting each option.
- [ ] **Define all configurable values** — Include: `max_visited_sites` (default 500), `max_history_per_tab` (default 80), `max_closed_tabs` (default 100), `sidebar_width` (default 240), `sidebar_mode` (default "pushed"), `animation_speed_ms` (default 200), `default_search_engine` (URL template), `homepage` (URL or "new-tab"), `theme` ("dark" or "light"), `new_tab_page` ("blank" or "homepage"), shield default on/off.
- [ ] **Watch config file for changes** — Use `ReadDirectoryChangesW` to watch the config directory. On change, reload and apply the diff without restarting the app.
- [ ] **Settings panel UI** — An in-app settings panel (accessible from command palette or a gear icon) that reads and writes `config.toml` through a form UI. Changes persist immediately.

---

## Phase 20 — Power User & Utility Features

### Duplicate Tab

- [ ] **Duplicate tab** — Right-click a tab row in the sidebar → "Duplicate Tab". Creates a new `Tab` with the same URL (and optionally same history stack). Opens immediately adjacent to the source tab.

### Tab Groups with Colors

- [ ] **Folder colour coding** — Extend the `Folder` struct with a `color: Option<RGB>` field. In the sidebar, render a colour swatch before the folder name. Provide a colour picker in the folder rename popover.
- [ ] **Group-level operations** — Right-click a folder to get options: Close All Tabs in Folder, Sleep All Tabs in Folder, Mute All Tabs in Folder, Duplicate Folder.

### Battery / Efficiency Mode

- [ ] **Detect battery vs AC power** — Use `GetSystemPowerStatus` to check power source. Subscribe to `WM_POWERBROADCAST` to react to power-source changes.
- [ ] **Aggressive tab sleeping on battery** — When on battery, automatically sleep all background tabs after a configurable idle timeout (default: 30 seconds). Show a battery indicator icon in the topbar when efficiency mode is active.
- [ ] **Reduced animation frequency on battery** — When efficiency mode is active, reduce the procedural background animation frame rate to 0 (static) and skip non-essential repaint timers.

### Self-Hosted Sync

- [ ] **Sync data format** — Define a portable sync bundle: a ZIP of `config.toml`, `.aster-state`, `bookmarks.tsv`, and optionally `downloads.tsv`. Encrypted with AES-256-GCM using a user-provided passphrase (derive key via Argon2).
- [ ] **WebDAV sync** — Allow the user to configure a WebDAV server URL + credentials. On a sync event (manual or scheduled), upload the encrypted bundle and download the remote bundle, then merge (last-write-wins per workspace/bookmark).
- [ ] **Local network sync** — Optionally discover other Aster instances on the LAN via mDNS and offer peer-to-peer sync over a local TCP connection.
- [ ] **Sync UI** — A Sync section in settings: configure sync target (WebDAV URL, local path), set passphrase, trigger manual sync, view last-sync timestamp.

### Mods / Extensions System

- [ ] **Define mod format** — A mod is a directory in `%APPDATA%\Aster\Mods\<mod-name>\` containing: `mod.toml` (name, version, author, description), optionally `inject.css` (injected into all pages), optionally `inject.js` (injected into all pages), optionally `shell.css` (injected into the shell chrome via custom GDI colours overrides specified as a palette TOML).
- [ ] **Mod loader** — On startup, enumerate `%APPDATA%\Aster\Mods\`. For each enabled mod, load `inject.css` and `inject.js` and register them to be injected via `AddScriptToExecuteOnDocumentCreated` and a CSS injection script.
- [ ] **Mods panel in settings** — List installed mods with enable/disable toggle, author, version, and a short description. A "Open Mods Folder" button opens File Explorer at the mods directory.

---

## Phase 21 — Code Architecture (Ongoing Refactor)

- [ ] **Modularize into a Cargo workspace** — Split `main.rs` into modules: `app/` (App struct, core logic, message loop), `ui/` (all GDI rendering: fonts, brushes, bitmaps, layout helpers), `webview/` (WebView2 lifecycle, event subscriptions, controller pool), `state/` (AppState struct, load/save, serialization, migration), `events/` (WM_* handler dispatch table), `drag/` (drag-and-drop state machine for both tabs and bookmarks), `config/` (config.toml parsing and watching).
- [ ] **Replace global mutable statics** — Eliminate all `static mut OLD_*_PROC` variables. Use a `Box<AppState>` stored as a pointer in `SetWindowLongPtrW(GWLP_USERDATA)` and retrieved in every `WndProc` call via `GetWindowLongPtrW`. This makes the app single-instance safe and eliminates UB from `static mut`.
- [ ] **Encapsulate `unsafe` Win32 calls in safe wrappers** — Create a `win32` module with functions like `fn create_window(...) -> Result<HWND>`, `fn set_timer(...) -> Result<u32>`, etc. All `unsafe` is confined to this module. All other modules call only safe Rust.
- [ ] **Implement selective region repainting** — Replace the single `refresh()` call with a dirty-region system. Each UI region (topbar, sidebar, content, status bar) has its own `RECT`. Only the changed regions are passed to `InvalidateRect`. A sidebar scroll should not cause the topbar or content to repaint.
- [ ] **Adopt typed IDs** — Replace raw `u64` IDs with newtype wrappers: `struct TabId(u64)`, `struct FolderId(u64)`, `struct WorkspaceId(u64)`. This prevents accidental mix-ups and makes API signatures self-documenting.
- [ ] **Error handling throughout** — Replace `unwrap()` / `expect()` with `?`-propagated `Result<T, AsterError>`. Define a top-level `AsterError` enum with variants for each subsystem failure mode. Log all errors to `%APPDATA%\Aster\aster.log` with timestamps.
- [ ] **Unit tests for state serialization** — Write tests that round-trip `AppState` through the TSV save/load functions and assert structural equality. Cover edge cases: empty workspaces, deeply nested folders, tabs with long histories.
- [ ] **Unit tests for frecency scoring** — Write tests that verify the scoring algorithm ranks recently-visited sites higher than older ones with more visits, and that sites not visited for >90 days decay below newly-visited ones.
- [ ] **Integrate a structured logging framework** — Use `tracing` crate (or equivalent) with a `tracing-subscriber` that writes structured JSON to the log file. Log every navigation, state save, download event, and WebView2 error with context fields.

---

## Phase 22 — QA, Visual Refinement & Final Polish

> **This phase is mandatory. Do not consider the build finished until every item below is ticked. Go back and fix anything that fails — repeat until the entire list is green.**

### Functional Correctness Pass

- [ ] **Audit every feature end-to-end** — Open the app fresh with no existing state file. Walk through every feature in Phases 1–21 in order. Verify each one works exactly as its spec describes. File a sub-task for every deviation found and fix it before continuing.
- [ ] **State persistence stress test** — Create 5 workspaces, 30 tabs across them with varied folder nesting, 10 bookmarks in nested folders, and 3 named sessions. Close the app. Reopen it. Verify every workspace, tab, folder, and bookmark is restored exactly — correct order, correct nesting depth, correct active tab per workspace.
- [ ] **Crash recovery test** — Force-kill the process while 10 tabs are open across 2 workspaces. Reopen. Verify the crash recovery prompt appears and correctly restores the pre-crash state.
- [ ] **Download manager end-to-end** — Start 3 concurrent downloads. Pause one, cancel one, let one complete. Verify all state transitions (progress bar, badge count, button states) are correct throughout.
- [ ] **Content blocking verification** — Load a page known to have ad requests (e.g. a news homepage). Open the Shields popover. Verify that blocked request count is non-zero and the listed domains are plausible ad/tracker domains.
- [ ] **Container isolation verification** — Log into a site in Container A. Open the same site in Container B. Verify the sessions are fully independent (different login state, different cookies).
- [ ] **Split view resize verification** — Enter split view. Drag the divider to extreme positions (10%/90%, 90%/10%, 50%/50%). Verify both WebView2 panels resize correctly with no overlap, clipping, or blank regions.
- [ ] **Peek panel verification** — Shift+click 5 different links on various pages. Verify the peek panel loads the correct URL each time, dismiss works, and "Open in Tab" correctly converts the peek into a real tab.
- [ ] **Import verification** — If Chrome, Edge, or Firefox is installed, run the import wizard. Verify imported bookmarks appear in the bookmarks panel with correct folder structure and that imported history items appear in the frecency autocomplete.

### Visual & UI Polish Pass

- [ ] **Full UI audit against the UI Quality Standards** — Go through every screen, panel, popover, and state defined in the UI Quality Standards section at the top of this document. For each standard (spacing, typography, colour, hover states, animations, icons, rounded corners, depth, empty states, loading states, error states, scrollbars), verify every UI surface complies. Fix every violation found.
- [ ] **Typography consistency check** — Open every panel and overlay in the app. Verify that font sizes, weights, and colours match the defined scale. No rogue font sizes. No text that's too small to read comfortably at 100% DPI. No text that lacks sufficient contrast against its background (minimum 4.5:1 ratio for body text).
- [ ] **Colour contrast audit** — For both dark and light themes, check every text/background combination. Every label, badge, button text, placeholder, and icon must meet WCAG AA contrast requirements.
- [ ] **Animation smoothness check** — Trigger every animated transition in the app (sidebar open/close, panel slide-ins, hover states, loading spinner, procedural background). Verify each runs at a smooth, consistent frame rate with no jank, stutter, or teleport artifacts.
- [ ] **Icon consistency audit** — Review every icon rendered in the app (topbar icons, sidebar icons, panel icons, badge icons, empty-state illustrations). Verify they all share the same visual style (stroke weight, corner rounding, optical size). Replace any that look out of place.
- [ ] **Empty state design check** — Trigger the empty state for every panel that has one: bookmarks (no bookmarks added), downloads (no downloads), history (fresh install), recently closed tabs (none closed yet), containers (default set visible). Verify each has a proper illustration + headline + subtitle — no blank panels.
- [ ] **DPI scaling check at 100%, 125%, 150%, and 200%** — Change Windows display scaling to each value and verify the shell, sidebar, topbar, address bar, and all panels render crisply with no blurry text, misaligned borders, or off-pixel icon rendering.
- [ ] **Window resize stress test** — Resize the window to extreme dimensions: very narrow (400px wide), very short (300px tall), maximized, and restored. Verify the layout adapts at every size with no overflow, clipping, or broken proportions.
- [ ] **Scrollbar styling check** — Trigger overflow in every scrollable container (tab list with 40+ tabs, bookmarks panel with 100+ entries, command palette with many results). Verify the scrollbar is thin, rounded, styled, auto-hides after 1.5s, and reappears on hover.

### Performance & Stability Pass

- [ ] **Memory usage benchmark** — Launch the app, open 10 tabs across 2 workspaces, wait 60 seconds, and record memory usage. Target: under 200MB for the shell process (excluding WebView2 renderer processes). If over target, profile and eliminate the largest allocations.
- [ ] **Startup time benchmark** — Measure time from process launch to first interactive frame (address bar focusable, sidebar visible) with a saved state of 20 tabs across 3 workspaces. Target: under 1.5 seconds on a mid-range machine. If over, profile and fix.
- [ ] **Repaint profiling** — Instrument the paint path. Verify that scrolling the sidebar does not repaint the topbar or content area. Verify that typing in the address bar does not repaint the sidebar. Verify that a tab loading spinner does not trigger a full-window repaint.
- [ ] **Long session stability test** — Run the app for 2 hours with normal browsing activity: open and close 50+ tabs, drag and reorder, switch workspaces 20+ times, trigger downloads and shields. Verify no memory leak (memory should not grow unboundedly), no crashes, no state corruption on save.
- [ ] **State file integrity test** — After the long session test above, inspect the saved `.aster-state` file. Verify it is valid TSV, all entries are well-formed, no truncation occurred, and the file loads correctly on a fresh reopen.

### Final Sign-Off

- [ ] **Re-read every task in Phases 1–21** — Go line by line. For any task that was implemented as a stub, approximation, or partial implementation, upgrade it to the full spec now.
- [ ] **Fix every known issue before this checkbox** — There must be zero known bugs, visual glitches, or incomplete features in the tracked issue list before this item is ticked.
- [ ] **The build is done when this checkbox is ticked — and not a moment before.**
