resource "aws_ecr_repository" "main" {
  name         = "${var.name_prefix}-newsletter"
  force_delete = true
}

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"
}

resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/${var.name_prefix}-newsletter"
  retention_in_days = 7
}

resource "aws_iam_role" "execution" {
  name = "${var.name_prefix}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "${var.name_prefix}-ecs-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [var.aurora_secret_arn]
    }]
  })
}

resource "aws_security_group" "fargate" {
  name        = "${var.name_prefix}-fargate-sg"
  description = "Fargate tasks"
  vpc_id      = var.vpc_id
}

resource "aws_security_group_rule" "fargate_egress_https" {
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.fargate.id
}

resource "aws_security_group_rule" "fargate_egress_aurora" {
  type                     = "egress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.fargate.id
  source_security_group_id = var.aurora_sg_id
}

# Allow Fargate → Aurora (adds rule to existing aurora SG)
resource "aws_security_group_rule" "aurora_ingress_fargate" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = var.aurora_sg_id
  source_security_group_id = aws_security_group.fargate.id
}

resource "aws_ecs_task_definition" "main" {
  family                   = "${var.name_prefix}-newsletter"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([{
    name  = "newsletter"
    image = "${aws_ecr_repository.main.repository_url}:${var.image_tag}"
    portMappings = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "DB_HOST",              value = var.db_host },
      { name = "DB_NAME",              value = var.db_name },
      { name = "DB_USER",              value = var.db_user },
      { name = "COGNITO_USER_POOL_ID", value = var.cognito_user_pool_id },
      { name = "COGNITO_CLIENT_ID",    value = var.cognito_client_id },
      { name = "AWS_REGION",           value = var.region },
      { name = "DEEP_DIVE_INTERVAL",   value = "0.05" },
      { name = "UVICORN_WORKERS",      value = tostring(var.uvicorn_workers) },
      { name = "ALLOW_CACHE_BYPASS",   value = var.allow_cache_bypass },
      { name = "env",                  value = var.app_env },
    ]
    secrets = [
      { name = "DB_PASSWORD", valueFrom = "${var.aurora_secret_arn}:password::" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.main.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "main" {
  name            = "${var.name_prefix}-newsletter-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.main.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.fargate.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }
}

resource "aws_appautoscaling_target" "main" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.main.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 0
  max_capacity       = 2

  depends_on = [aws_ecs_service.main]
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name_prefix}-cpu-scaling"
  service_namespace  = "ecs"
  resource_id        = aws_appautoscaling_target.main.resource_id
  scalable_dimension = aws_appautoscaling_target.main.scalable_dimension
  policy_type        = "TargetTrackingScaling"

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
