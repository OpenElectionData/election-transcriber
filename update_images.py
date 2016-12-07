
if __name__ == "__main__":
    from transcriber.tasks import ImageUpdater
    
    import argparse
    parser = argparse.ArgumentParser(description='Update images from document cloud')
    parser.add_argument('--overwrite', action='store_true',
                   help='Overwrite images with newer versions on the server')

    args = parser.parse_args()

    updater = ImageUpdater(overwrite=args.overwrite)
    updater.updateAllDocumentCloud()

