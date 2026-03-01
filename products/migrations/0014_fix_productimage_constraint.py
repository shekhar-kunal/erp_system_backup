from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0013_add_currency_to_product"),
    ]

    operations = [
        # Step 1: Remove the broken unique_together
        migrations.AlterUniqueTogether(
            name="productimage",
            unique_together=set(),
        ),
        # Step 2: Add the correct conditional unique constraint
        migrations.AddConstraint(
            model_name="productimage",
            constraint=models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="unique_primary_image_per_product",
            ),
        ),
    ]