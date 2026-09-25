project = "Archivist"
author = "CoffeesoftDotDev"

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
]

source_suffix = {
    ".md": "markdown",
}

exclude_patterns = ["_build"]
myst_title_to_header = True
myst_heading_anchors = 3
myst_enable_extensions = ["colon_fence"]

html_theme = "furo"
html_title = "Archivist"
html_logo = "assets/Archivist.png"
html_favicon = "assets/Archivist.png"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "navigation_with_keys": True,
    "sidebar_hide_name": False,
    "source_repository": "https://github.com/CoffeesoftDotDev/archivist/",
    "source_branch": "main",
    "source_directory": "docs/",
    "light_css_variables": {
        "color-brand-primary": "#a95508",
        "color-brand-content": "#864107",
    },
    "dark_css_variables": {
        "color-brand-primary": "#f2a94f",
        "color-brand-content": "#ffc06e",
    },
}

copybutton_prompt_text = r">>> |\.\.\. |\$ |PS> "
copybutton_prompt_is_regexp = True
