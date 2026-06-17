"""Blueprint registration for the Flask backend."""


def register_blueprints(app):
    from .auth_routes import bp as auth_bp
    from .system import bp as system_bp
    from .staff import bp as staff_bp
    from .nights import bp as nights_bp
    from .work_schedule import bp as work_bp
    from .absences import bp as absences_bp
    from .exports_routes import bp as exports_bp
    from .submissions import bp as submissions_bp
    from .swaps import bp as swaps_bp

    for bp in (auth_bp, system_bp, staff_bp, nights_bp, work_bp, absences_bp,
               exports_bp, submissions_bp, swaps_bp):
        app.register_blueprint(bp)
