(() => {
    const currentPath = window.location.pathname.replace(/\/+$/, '') || '/';
    const currentHash = window.location.hash;

    document.querySelectorAll('.topbar nav a').forEach((link) => {
        const target = new URL(link.href, window.location.href);
        if (target.origin !== window.location.origin) {
            return;
        }

        const targetPath = target.pathname.replace(/\/+$/, '') || '/';
        const isSectionLink = Boolean(target.hash);
        const matchesPath = targetPath === currentPath || (
            !isSectionLink && targetPath !== '/' && currentPath.startsWith(`${targetPath}/`)
        );
        const matchesLocation = !isSectionLink || target.hash === currentHash;

        if (matchesPath && matchesLocation) {
            link.classList.add('is-active');
            link.setAttribute('aria-current', isSectionLink ? 'location' : 'page');
        }
    });
})();