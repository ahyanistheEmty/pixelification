use windows::Win32::Foundation::COLORREF;

pub const fn rgb(r: u8, g: u8, b: u8) -> COLORREF {
    COLORREF(r as u32 | (g as u32) << 8 | (b as u32) << 16)
}

#[derive(Clone, Copy, Debug)]
pub struct ThemePalette {
    pub background: COLORREF,
    pub surface: COLORREF,
    pub surface_raised: COLORREF,
    pub border: COLORREF,
    pub text_primary: COLORREF,
    pub text_secondary: COLORREF,
    pub accent: COLORREF,
    pub accent_hover: COLORREF,
    pub hover: COLORREF,
    pub active: COLORREF,
    pub scrollbar: COLORREF,
    pub scrollbar_hover: COLORREF,
    pub divider: COLORREF,
    pub surface_sunken: COLORREF,
    pub danger: COLORREF,
    pub success: COLORREF,
    pub warning: COLORREF,
}

pub const DARK: ThemePalette = ThemePalette {
    background: rgb(18, 18, 22),
    surface: rgb(26, 26, 32),
    surface_raised: rgb(34, 34, 42),
    border: rgb(46, 46, 54),
    text_primary: rgb(225, 225, 235),
    text_secondary: rgb(155, 155, 165),
    accent: rgb(99, 125, 255),
    accent_hover: rgb(125, 145, 255),
    hover: rgb(42, 42, 52),
    active: rgb(50, 50, 62),
    scrollbar: rgb(60, 60, 70),
    scrollbar_hover: rgb(80, 80, 92),
    divider: rgb(42, 42, 50),
    surface_sunken: rgb(14, 14, 18),
    danger: rgb(235, 85, 85),
    success: rgb(70, 200, 130),
    warning: rgb(240, 185, 50),
};

pub const LIGHT: ThemePalette = ThemePalette {
    background: rgb(245, 245, 248),
    surface: rgb(255, 255, 255),
    surface_raised: rgb(250, 250, 252),
    border: rgb(220, 220, 226),
    text_primary: rgb(30, 30, 38),
    text_secondary: rgb(110, 110, 120),
    accent: rgb(75, 100, 235),
    accent_hover: rgb(55, 80, 215),
    hover: rgb(240, 240, 245),
    active: rgb(235, 235, 242),
    scrollbar: rgb(200, 200, 208),
    scrollbar_hover: rgb(180, 180, 190),
    divider: rgb(230, 230, 236),
    surface_sunken: rgb(238, 238, 242),
    danger: rgb(200, 55, 55),
    success: rgb(45, 170, 100),
    warning: rgb(210, 155, 20),
};

pub enum Theme {
    Dark,
    Light,
}

impl Theme {
    pub fn palette(&self) -> &ThemePalette {
        match self {
            Theme::Dark => &DARK,
            Theme::Light => &LIGHT,
        }
    }
}
