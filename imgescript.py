from google.cloud import aiplatform
from vertexai.preview.vision_models import ImageGenerationModel

def generate_capybara():
    aiplatform.init(
        project="gen-lang-client-0167473511",
        location="us-central1"
    )

    model = ImageGenerationModel.from_pretrained(
        "imagen-4.0-fast-generate-001"
    )

    print("Generando imagen del carpincho...")

    images = model.generate_images(
        prompt="A cute capybara wearing a small crown, sitting peacefully by a river, digital art style.",
        number_of_images=1,
    )

    images[0].save(location="capybara_test.png")

    print("¡Listo!")

if __name__ == "__main__":
    generate_capybara()