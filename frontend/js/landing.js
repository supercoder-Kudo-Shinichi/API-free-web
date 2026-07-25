/**
 * Landing Page - Animations & Interactions.
 * 
 * All animations use vanilla JS for maximum performance (60 FPS).
 */
(function() {
    'use strict';

    // ==========================================
    // Intersection Observer for Reveal Animations
    // ==========================================
    function initRevealAnimations() {
        const reveals = document.querySelectorAll('.reveal');
        
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('visible');
                        observer.unobserve(entry.target);
                    }
                });
            },
            {
                threshold: 0.1,
                rootMargin: '0px 0px -50px 0px',
            }
        );

        reveals.forEach(el => observer.observe(el));
    }

    // ==========================================
    // Counter Animation
    // ==========================================
    function initCounterAnimation() {
        const counters = document.querySelectorAll('[data-count]');
        
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const target = parseInt(entry.target.getAttribute('data-count'));
                        animateCounter(entry.target, target);
                        observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.5 }
        );

        counters.forEach(el => observer.observe(el));
    }

    function animateCounter(element, target) {
        const duration = 2000;
        const steps = 60;
        const increment = target / steps;
        let current = 0;
        let step = 0;

        function update() {
            step++;
            current = Math.min(current + increment, target);
            element.textContent = Math.floor(current).toLocaleString();
            
            if (step < steps) {
                requestAnimationFrame(update);
            } else {
                element.textContent = target.toLocaleString() + '+';
            }
        }

        requestAnimationFrame(update);
    }

    // ==========================================
    // Smooth Scroll for Navigation Links
    // ==========================================
    function initSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function(e) {
                const targetId = this.getAttribute('href');
                if (targetId === '#') return;
                
                const target = document.querySelector(targetId);
                if (target) {
                    e.preventDefault();
                    
                    const headerOffset = 80;
                    const elementPosition = target.getBoundingClientRect().top;
                    const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

                    window.scrollTo({
                        top: offsetPosition,
                        behavior: 'smooth',
                    });

                    // Close mobile nav if open
                    document.querySelector('.nav-links')?.classList.remove('mobile-open');
                }
            });
        });
    }

    // ==========================================
    // Mobile Navigation Toggle
    // ==========================================
    function initMobileNav() {
        const toggle = document.querySelector('.nav-mobile-toggle');
        const navLinks = document.querySelector('.nav-links');

        if (toggle && navLinks) {
            toggle.addEventListener('click', () => {
                navLinks.classList.toggle('mobile-open');
            });

            // Close on click outside
            document.addEventListener('click', (e) => {
                if (!toggle.contains(e.target) && !navLinks.contains(e.target)) {
                    navLinks.classList.remove('mobile-open');
                }
            });
        }
    }

    // ==========================================
    // Navbar Background on Scroll
    // ==========================================
    function initNavbarScroll() {
        const nav = document.querySelector('.nav');
        let lastScroll = 0;

        window.addEventListener('scroll', () => {
            const currentScroll = window.pageYOffset;
            
            if (currentScroll > 100) {
                nav.classList.add('nav-scrolled');
            } else {
                nav.classList.remove('nav-scrolled');
            }

            lastScroll = currentScroll;
        }, { passive: true });
    }

    // ==========================================
    // FAQ Accordion
    // ==========================================
    function initFAQ() {
        document.querySelectorAll('.faq-question').forEach(question => {
            question.addEventListener('click', () => {
                const item = question.parentElement;
                const isActive = item.classList.contains('active');

                // Close all FAQ items
                document.querySelectorAll('.faq-item').forEach(i => {
                    i.classList.remove('active');
                    const answer = i.querySelector('.faq-answer');
                    if (answer) {
                        answer.style.maxHeight = '0';
                    }
                });

                // Open clicked item if it wasn't active
                if (!isActive) {
                    item.classList.add('active');
                    const answer = item.querySelector('.faq-answer');
                    if (answer) {
                        answer.style.maxHeight = answer.scrollHeight + 'px';
                    }
                }
            });
        });
    }

    // ==========================================
    // Mouse Parallax Effect (subtle)
    // ==========================================
    function initParallax() {
        const hero = document.querySelector('.hero');
        if (!hero) return;

        window.addEventListener('mousemove', (e) => {
            const x = (e.clientX / window.innerWidth - 0.5) * 10;
            const y = (e.clientY / window.innerHeight - 0.5) * 10;
            
            const gradient = hero.querySelector('.hero-gradient');
            if (gradient) {
                gradient.style.transform = `translate(${x}px, ${y}px)`;
            }
        }, { passive: true });
    }

    // ==========================================
    // Floating Animation for Feature Cards
    // ==========================================
    function initFloatingCards() {
        const cards = document.querySelectorAll('.feature-card');
        
        cards.forEach((card, index) => {
            const duration = 3 + (index * 0.5);
            const delay = index * 0.2;
            
            card.style.animation = `floatCard ${duration}s ease-in-out ${delay}s infinite`;
        });
    }

    // Add keyframe for floating animation dynamically
    const style = document.createElement('style');
    style.textContent = `
        @keyframes floatCard {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-6px); }
        }
    `;
    document.head.appendChild(style);

    // ==========================================
    // Initialize All Animations
    // ==========================================
    function init() {
        initRevealAnimations();
        initCounterAnimation();
        initSmoothScroll();
        initMobileNav();
        initNavbarScroll();
        initFAQ();
        initParallax();
        initFloatingCards();

        // Add nav-scrolled class initial check
        if (window.pageYOffset > 100) {
            document.querySelector('.nav')?.classList.add('nav-scrolled');
        }
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
