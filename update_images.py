
if __name__ == "__main__":
    from transcriber.tasks import update_all_document_cloud
    update_all_document_cloud()

    # from transcriber import create_app

    # app = create_app()

    # with app.test_request_context():
    #     from transcriber.database import db
    #     from transcriber.models import FormMeta
    #     from transcriber.views import update_task_images

    #     all_forms = db.session.query(FormMeta).all()
    #     for form in all_forms:
    #         update_task_images(form.id)
