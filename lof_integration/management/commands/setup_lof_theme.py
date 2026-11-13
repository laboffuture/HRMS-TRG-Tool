"""
python manage.py setup_lof_theme

Creates (or updates) the "LOF Blue" colour theme built around the LOF brand
blue #1C4D8C, makes it the default (login page) theme, and assigns it to every
company. Replaces 1.x's static/css/lof-theme.css, whose .oh-btn overrides no
longer reach the 2.x Tailwind theme (colours come from HorillaColorTheme).

Idempotent — safe to re-run. Use --no-assign to only create the theme.
"""

from django.core.management.base import BaseCommand

LOF_THEME = {
    "name": "LOF Blue",
    "description": "LOF brand theme (primary #1C4D8C)",
    "primary_50": "#f5f8fc",
    "primary_100": "#eaf0f8",
    "primary_200": "#d3e0f0",
    "primary_300": "#b4cbe6",
    "primary_400": "#7fa3d1",
    "primary_500": "#aec3e0",
    "primary_600": "#1C4D8C",
    "primary_700": "#163d70",
    "primary_800": "#112f57",
    "primary_900": "#0b1f3a",
    "dark_50": "#E6E6E6",
    "dark_100": "#A8A8A8",
    "dark_200": "#515151",
    "dark_300": "#0f2a4d",
    "dark_400": "#64748B",
    "dark_500": "#07152a",
    "dark_600": "#000000",
    "secondary_50": "#f8fafc",
    "secondary_100": "#f1f5f9",
    "secondary_200": "#e2e8f0",
    "secondary_300": "#cbd5e1",
    "secondary_400": "#d3e0f0",
    "secondary_500": "#aec3e0",
    "secondary_600": "#1C4D8C",
    "secondary_700": "#334155",
    "secondary_800": "#1e293b",
    "secondary_900": "#0f172a",
}


class Command(BaseCommand):
    help = "Create the LOF Blue colour theme, make it default and assign it to all companies"

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-assign",
            action="store_true",
            help="Only create/update the theme; do not make it default or assign it.",
        )

    def handle(self, *args, **options):
        from base.models import Company
        from horilla_theme.models import CompanyTheme, HorillaColorTheme

        data = dict(LOF_THEME)
        name = data.pop("name")
        theme, created = HorillaColorTheme.objects.update_or_create(
            name=name, defaults=data
        )
        self.stdout.write(
            self.style.SUCCESS(f"{'Created' if created else 'Updated'} theme: {name}")
        )

        if options["no_assign"]:
            return

        theme.is_default = True
        theme.save()  # model.save() unsets any other default
        assigned = 0
        for company in Company.objects.all():
            CompanyTheme.objects.update_or_create(
                company=company, defaults={"theme": theme}
            )
            assigned += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Set '{name}' as default and assigned it to {assigned} company(ies)."
            )
        )
