{
    "name": "Nolte Mitarbeiterportal",
    "version": "19.0.1.0.0",
    "category": "Human Resources",
    "summary": "Mobiles Kachelportal für Mitarbeiterbereiche",
    "author": "Nolte Engineering",
    "license": "LGPL-3",
    "depends": ["website"],
    "data": [
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "nolte_mitarbeiterportal/static/src/scss/portal.scss",
        ],
    },
    "application": True,
    "installable": True,
}
