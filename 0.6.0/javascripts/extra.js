// Remove the sidebar from Jupyter notebooks: https://github.com/danielfrg/mkdocs-jupyter/issues/99
document$.subscribe(function () {
    // First check if the page contains a notebook-related class
    if (document.querySelector('.jp-Notebook')) {
        document.querySelector("div.md-sidebar.md-sidebar--secondary").remove();
    }
});