terraform {
  backend "s3" {
    bucket         = "newsletter-tfstate-730335358053"
    key            = "dev/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "newsletter-tfstate-lock"
    encrypt        = true
  }
}
