class Pagination {
    constructor(containerId, totalPages, onChange) {
        this.container = document.getElementById(containerId);
        this.totalPages = totalPages;
        this.currentPage = 1;
        this.onChange = onChange;

        this.btnPrev = this.container.querySelector('#btnPrev');
        this.btnNext = this.container.querySelector('#btnNext');
        this.pgNums = this.container.querySelector('#pgNums');

        this.init();
    }

    init() {
        this.render();
        this.btnPrev.addEventListener('click', () => this.goTo(this.currentPage - 1));
        this.btnNext.addEventListener('click', () => this.goTo(this.currentPage + 1));
    }

    goTo(page) {
        if (page < 1 || page > this.totalPages) return;
        this.currentPage = page;
        this.render();
        if (this.onChange) this.onChange(page);
    }

    getVisiblePages() {
        const pages = [];
        const total = this.totalPages;
        const cur = this.currentPage;

        if (total <= 5) {
            for (let i = 1; i <= total; i++) pages.push(i);
        } else {
            pages.push(1);
            if (cur > 3) pages.push('...');
            const start = Math.max(2, cur - 1);
            const end = Math.min(total - 1, cur + 1);
            for (let i = start; i <= end; i++) pages.push(i);
            if (cur < total - 2) pages.push('...');
            pages.push(total);
        }

        return pages;
    }

    render() {
        // Mise à jour des boutons prev/next
        this.btnPrev.disabled = this.currentPage === 1;
        this.btnNext.disabled = this.currentPage === this.totalPages;

        // Génération des boutons de pages
        this.pgNums.innerHTML = this.getVisiblePages()
            .map(p =>
                p === '...'
                    ? `<span class="pg-dots">...</span>`
                    : `<button class="pg-btn${p === this.currentPage ? ' active' : ''}"
                        data-page="${p}">${p}</button>`
            )
            .join('');

        // Événements sur les boutons de pages
        this.pgNums.querySelectorAll('.pg-btn').forEach(btn => {
            btn.addEventListener('click', () => this.goTo(Number(btn.dataset.page)));
        });
    }
}
