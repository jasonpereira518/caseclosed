(function () {
    "use strict";

    const header = document.querySelector("[data-header]");
    const navToggle = document.querySelector("[data-nav-toggle]");
    const navLinks = document.querySelector("[data-nav-links]");
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function updateHeader() {
        if (header) header.classList.toggle("scrolled", window.scrollY > 12);
    }

    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });

    function closeNavigation() {
        if (!navToggle || !navLinks) return;
        navToggle.setAttribute("aria-expanded", "false");
        navLinks.classList.remove("open");
        document.body.classList.remove("nav-open");
    }

    if (navToggle && navLinks) {
        navToggle.addEventListener("click", function () {
            const shouldOpen = navToggle.getAttribute("aria-expanded") !== "true";
            navToggle.setAttribute("aria-expanded", String(shouldOpen));
            navLinks.classList.toggle("open", shouldOpen);
            document.body.classList.toggle("nav-open", shouldOpen);
        });

        navLinks.querySelectorAll("a").forEach(function (link) {
            link.addEventListener("click", closeNavigation);
        });

        window.addEventListener("resize", function () {
            if (window.innerWidth > 820) closeNavigation();
        });
    }

    /* ---------------------------------------------------------------------
       Hero product frame.

       The hero used to contain a hand-built replica of the dashboard, driven
       by its own tab controller here. It now frames the real workspace at
       /demo, rendered at a desktop viewport and scaled to fit — so the only
       thing left to do is compute the scale factor, which CSS cannot derive
       from the container's measured width.
       ------------------------------------------------------------------- */
    const productFrame = document.querySelector("[data-product-frame]");

    if (productFrame) {
        const AUTHORED_WIDTH = 1440;
        const viewport = productFrame.querySelector(".hero-product-viewport");

        const fitProduct = function () {
            if (!viewport) return;
            const width = viewport.clientWidth;
            if (!width) return;
            viewport.style.setProperty("--product-scale", String(width / AUTHORED_WIDTH));
        };

        fitProduct();

        if ("ResizeObserver" in window) {
            new ResizeObserver(fitProduct).observe(viewport);
        } else {
            window.addEventListener("resize", fitProduct, { passive: true });
        }
    }

    const revealItems = document.querySelectorAll(".reveal");
    const fragmentedDemo = document.querySelector(".fragmented-demo");
    const workflowSteps = document.querySelector(".workflow-steps");

    if (reduceMotion || !("IntersectionObserver" in window)) {
        revealItems.forEach(function (item) {
            item.classList.add("is-visible");
        });
        if (fragmentedDemo) fragmentedDemo.classList.add("in-view");
        if (workflowSteps) workflowSteps.classList.add("in-view");
    } else {
        const revealObserver = new IntersectionObserver(function (entries, observer) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.14, rootMargin: "0px 0px -45px" });

        revealItems.forEach(function (item) {
            revealObserver.observe(item);
        });

        if (fragmentedDemo) {
            const fragmentObserver = new IntersectionObserver(function (entries, observer) {
                if (!entries[0].isIntersecting) return;
                fragmentedDemo.classList.add("in-view");
                observer.unobserve(fragmentedDemo);
            }, { threshold: 0.3 });
            fragmentObserver.observe(fragmentedDemo);
        }

        if (workflowSteps) {
            const workflowObserver = new IntersectionObserver(function (entries, observer) {
                if (!entries[0].isIntersecting) return;
                workflowSteps.classList.add("in-view");
                observer.unobserve(workflowSteps);
            }, { threshold: 0.35 });
            workflowObserver.observe(workflowSteps);
        }
    }

    const featureButtons = Array.from(document.querySelectorAll("[data-feature]"));
    const featureLayout = document.querySelector(".feature-layout");
    const featureSection = document.querySelector(".product-section");
    const featureList = document.querySelector(".feature-list");
    const previewState = document.querySelector("[data-preview-state]");
    const previewCanvas = document.querySelector("[data-preview-canvas]");
    const previewEyebrow = document.querySelector("[data-preview-eyebrow]");
    const previewTitle = document.querySelector("[data-preview-title]");
    const previewRecords = document.querySelector("[data-preview-records]");
    let featureTimer = null;
    let featureIndex = 0;
    let userSelectedFeature = false;

    /* Preview content is the Rivera v. Northline matter from
       static/demo-fixture.json — the same synthetic matter the hero iframe
       runs on. Every case name is fictional by design; never add a real one
       (tests/test_landing_fixture_alignment.py enforces both). */
    const featureContent = {
        record: {
            status: "Record organized",
            eyebrow: "MATTER RECORD",
            title: "Five documents, one working record",
            className: "",
            rows: [
                ["PDF", "Complaint.pdf", "Filed Jul 15 · Analyzed", "✓"],
                ["PDF", "Incident_Report.pdf", "Clear conditions recorded · Analyzed", "✓"],
                ["DOC", "Rivera_Statement.docx", "Client statement · Analyzed", "✓"],
                ["TXT", "Dispatch_Log.txt", "Telemetry after clock-out · Analyzed", "✓"]
            ]
        },
        timeline: {
            status: "7 events connected",
            eyebrow: "CHRONOLOGY",
            title: "The facts, arranged in time",
            className: "timeline-state",
            rows: [
                ["MAR 14", "Collision at Kellner & 7th", "Marked crossing, approx. 07:52", ""],
                ["MAR 14", "Vehicle transmits location at 08:33", "41 minutes after recorded clock-out", ""],
                ["JUN 28", "Northline denies liability", "Asserts driver had ended his shift", ""],
                ["JUL 15", "Complaint filed", "Franklin County Court of Common Pleas", ""]
            ]
        },
        issues: {
            status: "5 issues identified",
            eyebrow: "STRUCTURED ANALYSIS",
            title: "Legal questions connected to the facts",
            className: "issue-state",
            rows: [
                ["01", "Scope of employment", "Route completion after clock-out", "Open"],
                ["02", "Telemetry vs. timekeeping", "Dispatch log contradicts records", "Review"],
                ["03", "Comparative fault", "Entry as the signal changed", "Open"],
                ["04", "Negligent supervision", "Independent count against Northline", "Open"]
            ]
        },
        authority: {
            status: "5 authorities ranked",
            eyebrow: "CASE RESEARCH",
            title: "Authority ranked by matter fit",
            className: "authority-state",
            rows: [
                ["91", "Alvarado v. Crestmoor Freight Co.", "Fict. 2019 · Scope of employment", "View"],
                ["84", "Petrakis v. Halvern Distribution", "Fict. 2022 · Negligent supervision", "View"],
                ["77", "Okonkwo v. Bayline Transit", "Fict. 2016 · Comparative fault", "View"],
                ["61", "Denholm v. Riverbend Carriers", "Fict. 2008 · Adverse authority", "View"]
            ]
        },
        draft: {
            status: "Draft ready",
            eyebrow: "LEGAL MEMORANDUM",
            title: "A first draft grounded in this matter",
            className: "draft-state",
            rows: [
                ["", "Question Presented", "Whether Northline is vicariously liable where its dispatch telemetry places the vehicle on its assigned route forty-one minutes after the operator's recorded clock-out.", ""],
                ["", "Brief Answer", "Probably yes, on the present record. The telemetry contradicts the employer's own timekeeping; the principal risk is comparative fault.", ""],
                ["", "Analysis", "The memorandum connects the dispatch log, the scope-of-employment authorities, and the comparative-fault exposure collected in this matter.", ""]
            ]
        }
    };

    function createPreviewRow(row, index) {
        const wrapper = document.createElement("div");
        wrapper.style.animationDelay = String(index * 55) + "ms";

        const badge = document.createElement("span");
        badge.textContent = row[0];
        const copy = document.createElement("p");
        const title = document.createElement("strong");
        title.textContent = row[1];
        const detail = document.createElement("small");
        detail.textContent = row[2];
        const action = document.createElement("b");
        action.textContent = row[3];

        copy.append(title, detail);
        wrapper.append(badge, copy, action);
        return wrapper;
    }

    function selectFeature(featureName, fromUser) {
        const content = featureContent[featureName];
        if (!content || !previewRecords) return;

        featureButtons.forEach(function (button) {
            const isActive = button.dataset.feature === featureName;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-selected", String(isActive));
            if (isActive) {
                featureIndex = featureButtons.indexOf(button);
                if (!fromUser && featureList && window.innerWidth <= 600) {
                    featureList.scrollTo({
                        left: Math.max(0, button.offsetLeft - 24),
                        behavior: reduceMotion ? "auto" : "smooth"
                    });
                }
            }
        });

        if (previewState) previewState.textContent = content.status;
        if (previewEyebrow) previewEyebrow.textContent = content.eyebrow;
        if (previewTitle) previewTitle.textContent = content.title;
        if (previewCanvas) previewCanvas.dataset.state = featureName;

        previewRecords.className = "preview-records" + (content.className ? " " + content.className : "");
        previewRecords.replaceChildren();
        content.rows.forEach(function (row, index) {
            previewRecords.appendChild(createPreviewRow(row, index));
        });

        if (fromUser) {
            userSelectedFeature = true;
            stopFeatureDemo();
        }
    }

    featureButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            selectFeature(button.dataset.feature, true);
        });
    });

    function startFeatureDemo() {
        if (reduceMotion || userSelectedFeature || featureTimer || featureButtons.length < 2) return;
        if (featureLayout) featureLayout.classList.add("is-auto");
        featureTimer = window.setInterval(function () {
            if (document.hidden) return;
            featureIndex = (featureIndex + 1) % featureButtons.length;
            selectFeature(featureButtons[featureIndex].dataset.feature, false);
        }, 5600);
    }

    function stopFeatureDemo() {
        if (featureTimer) window.clearInterval(featureTimer);
        featureTimer = null;
        if (featureLayout) featureLayout.classList.remove("is-auto");
    }

    if (featureSection && featureButtons.length && !reduceMotion && "IntersectionObserver" in window) {
        const featureObserver = new IntersectionObserver(function (entries) {
            if (entries[0].isIntersecting) startFeatureDemo();
            else stopFeatureDemo();
        }, { threshold: 0.3 });
        featureObserver.observe(featureSection);
    }

    const outcomeRow = document.querySelector(".outcome-row");
    const outcomeNumbers = Array.from(document.querySelectorAll("[data-count]"));

    function animateOutcomeNumbers() {
        const duration = 780;
        const startedAt = performance.now();

        outcomeNumbers.forEach(function (number) {
            number.textContent = "0";
        });

        function draw(now) {
            const progress = Math.min(1, (now - startedAt) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            outcomeNumbers.forEach(function (number) {
                const target = Number(number.dataset.count);
                number.textContent = String(Math.round(target * eased));
            });
            if (progress < 1) window.requestAnimationFrame(draw);
        }

        window.requestAnimationFrame(draw);
    }

    if (outcomeRow && outcomeNumbers.length && !reduceMotion && "IntersectionObserver" in window) {
        const outcomeObserver = new IntersectionObserver(function (entries, observer) {
            if (!entries[0].isIntersecting) return;
            animateOutcomeNumbers();
            observer.unobserve(outcomeRow);
        }, { threshold: 0.45 });
        outcomeObserver.observe(outcomeRow);
    }

    const faqItems = document.querySelectorAll(".faq-list details");
    faqItems.forEach(function (item) {
        item.addEventListener("toggle", function () {
            if (!item.open) return;
            faqItems.forEach(function (otherItem) {
                if (otherItem !== item) otherItem.removeAttribute("open");
            });
        });
    });
})();
