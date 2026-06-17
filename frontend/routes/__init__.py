"""Blueprint registration for the Flask backend."""


def register_blueprints(app):
    from .system import bp as system_bp
    from .staff import bp as staff_bp
    from .nights import bp as nights_bp
    from .work_schedule import bp as work_bp
    from .absences import bp as absences_bp

    for bp in (system_bp, staff_bp, nights_bp, work_bp, absences_bp):
        app.register_blueprint(bp)
