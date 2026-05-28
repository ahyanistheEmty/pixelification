use std::collections::HashMap;
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryEntry {
    pub url: String,
    pub title: String,
    pub visited_at: u64,
    pub scroll_position: i32,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum ThemeMode {
    Auto,
    ForceDark,
    ForceLight,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TabId(pub u64);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct FolderId(pub u64);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct WorkspaceId(pub u64);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tab {
    pub id: TabId,
    pub title: String,
    pub url: String,
    pub is_pinned: bool,
    pub is_sleeping: bool,
    pub is_loading: bool,
    pub scroll_offset: i32,
    pub history: Vec<HistoryEntry>,
    pub history_index: usize,
    pub site_theme: ThemeMode,
    pub container_id: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Folder {
    pub id: FolderId,
    pub name: String,
    pub children: Vec<TabOrFolder>,
    pub is_collapsed: bool,
    pub is_pinned: bool,
    pub color: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TabOrFolder {
    Tab(Tab),
    Folder(Folder),
}

impl TabOrFolder {
    pub fn title(&self) -> &str {
        match self {
            TabOrFolder::Tab(t) => &t.title,
            TabOrFolder::Folder(f) => &f.name,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Workspace {
    pub id: WorkspaceId,
    pub name: String,
    pub color: String,
    pub icon: String,
    pub tabs: Vec<TabOrFolder>,
    pub active_tab_id: Option<TabId>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppState {
    pub workspaces: Vec<Workspace>,
    pub active_workspace_index: usize,
    pub closed_tabs: Vec<ClosedTabInfo>,
    pub sidebar_mode: String,
    pub sidebar_width: i32,
    pub theme: String,
    pub visited_sites: HashMap<String, VisitedSite>,
    pub next_tab_id: u64,
    pub next_folder_id: u64,
    pub next_workspace_id: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClosedTabInfo {
    pub title: String,
    pub url: String,
    pub closed_at: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VisitedSite {
    pub url: String,
    pub title: String,
    pub visit_count: u32,
    pub last_visited: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Bookmark {
    pub id: u64,
    pub title: String,
    pub url: String,
    pub created_at: u64,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BookmarkFolder {
    pub id: u64,
    pub name: String,
    pub children: Vec<BookmarkOrFolder>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum BookmarkOrFolder {
    Bookmark(Bookmark),
    Folder(BookmarkFolder),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Download {
    pub id: u64,
    pub url: String,
    pub filename: String,
    pub total_bytes: u64,
    pub received_bytes: u64,
    pub state: DownloadState,
    pub started_at: u64,
    pub completed_at: Option<u64>,
    pub local_path: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum DownloadState {
    Pending,
    InProgress,
    Paused,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Container {
    pub id: u64,
    pub name: String,
    pub color: String,
    pub icon: String,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            workspaces: vec![Workspace {
                id: WorkspaceId(1),
                name: "Default".into(),
                color: "#637dff".into(),
                icon: "\u{1F310}".into(),
                tabs: vec![],
                active_tab_id: None,
            }],
            active_workspace_index: 0,
            closed_tabs: vec![],
            sidebar_mode: "pushed".into(),
            sidebar_width: 240,
            theme: "dark".into(),
            visited_sites: HashMap::new(),
            next_tab_id: 2,
            next_folder_id: 1,
            next_workspace_id: 2,
        }
    }
}

impl AppState {
    pub fn active_workspace(&self) -> &Workspace {
        &self.workspaces[self.active_workspace_index]
    }

    pub fn active_workspace_mut(&mut self) -> &mut Workspace {
        &mut self.workspaces[self.active_workspace_index]
    }

    pub fn count_tabs(children: &[TabOrFolder]) -> usize {
        children.iter().map(|c| match c {
            TabOrFolder::Tab(_) => 1,
            TabOrFolder::Folder(f) => Self::count_tabs(&f.children),
        }).sum()
    }
}
