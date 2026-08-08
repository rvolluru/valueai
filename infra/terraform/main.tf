data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs                       = slice(data.aws_availability_zones.available.names, 0, 2)
  cloudwatch_log_group_name = var.create_cloudwatch_log_group ? aws_cloudwatch_log_group.api[0].name : var.existing_cloudwatch_log_group_name
  ecr_repository_url        = var.create_ecr_repository ? aws_ecr_repository.api[0].repository_url : var.existing_ecr_repository_url
}

resource "aws_vpc" "this" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "${var.project_name}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.project_name}-igw" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(aws_vpc.this.cidr_block, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.project_name}-public-${count.index + 1}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(aws_vpc.this.cidr_block, 8, count.index + 10)
  availability_zone = local.azs[count.index]
  tags              = { Name = "${var.project_name}-private-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_s3_bucket" "uploads" {
  bucket_prefix = "${var.project_name}-uploads-"
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD", "PUT", "POST"]
    allowed_origins = split(",", var.cors_allow_origins)
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

resource "aws_ecr_repository" "api" {
  count                = var.create_ecr_repository ? 1 : 0
  name                 = "${var.project_name}-api"
  image_tag_mutability = "MUTABLE"
}

resource "aws_cloudwatch_log_group" "api" {
  count             = var.create_cloudwatch_log_group ? 1 : 0
  name              = "/ecs/${var.project_name}"
  retention_in_days = 14
}

resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "ALB security group"
  vpc_id      = aws_vpc.this.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ecs" {
  name   = "${var.project_name}-ecs-sg"
  vpc_id = aws_vpc.this.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name   = "${var.project_name}-rds-sg"
  vpc_id = aws_vpc.this.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.project_name}-postgres"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = true
  publicly_accessible    = false
}

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-task-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_s3" {
  name = "${var.project_name}-task-s3-policy"
  role = aws_iam_role.ecs_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.uploads.arn,
          "${aws_s3_bucket.uploads.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_ecs_cluster" "this" {
  name = "${var.project_name}-cluster"
}

resource "aws_lb" "api" {
  name               = substr("${var.project_name}-alb", 0, 32)
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
  idle_timeout       = 180
}

resource "aws_lb_target_group" "api" {
  name        = substr("${var.project_name}-tg", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.this.id

  health_check {
    path = "/v1/health"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = var.api_certificate_arn == "" ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.api.arn
    }
  }

  dynamic "default_action" {
    for_each = var.api_certificate_arn == "" ? [] : [1]
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = var.api_certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.api.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.api_certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_route53_record" "api" {
  count   = var.create_api_dns_record && var.route53_zone_id != "" && var.api_domain_name != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.api_domain_name
  type    = "A"

  alias {
    name                   = aws_lb.api.dns_name
    zone_id                = aws_lb.api.zone_id
    evaluate_target_health = true
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name         = "api"
      image        = var.container_image
      essential    = true
      portMappings = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }]
      environment = [
        { name = "APP_ENV", value = var.app_env },
        { name = "API_KEY", value = var.api_key },
        { name = "VERSION", value = "0.1.0" },
        { name = "STORAGE_BACKEND", value = "s3" },
        { name = "S3_BUCKET", value = aws_s3_bucket.uploads.bucket },
        { name = "S3_REGION", value = var.aws_region },
        { name = "DATABASE_URL", value = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:5432/${var.db_name}" },
        { name = "OPENAI_API_KEY", value = var.openai_api_key },
        { name = "GEMINI_API_KEY", value = var.gemini_api_key },
        { name = "PHOTOROOM_API_KEY", value = var.photoroom_api_key },
        { name = "IMAGE_STAGING_PHOTOROOM_ENABLED", value = tostring(var.image_staging_photoroom_enabled) },
        { name = "PHOTOROOM_BACKGROUND_COLOR", value = var.photoroom_background_color },
        { name = "PHOTOROOM_OUTPUT_FORMAT", value = var.photoroom_output_format },
        { name = "PHOTOROOM_OUTPUT_SIZE", value = var.photoroom_output_size },
        { name = "STRIPE_SECRET_KEY", value = var.stripe_secret_key },
        { name = "STRIPE_PUBLISHABLE_KEY", value = var.stripe_publishable_key },
        { name = "CLERK_ENABLED", value = tostring(var.clerk_enabled) },
        { name = "CLERK_ISSUER", value = var.clerk_issuer },
        { name = "CLERK_JWKS_URL", value = var.clerk_jwks_url },
        { name = "CLERK_AUDIENCE", value = var.clerk_audience },
        { name = "CLERK_AUTHORIZED_PARTIES", value = var.clerk_authorized_parties },
        { name = "CORS_ALLOW_ORIGINS", value = var.cors_allow_origins },
        { name = "BRAND_ENABLE_GPT_VISION", value = tostring(var.brand_enable_gpt_vision) },
        { name = "GPT_ITEM_PROFILE_ENABLED", value = tostring(var.gpt_item_profile_enabled) },
        { name = "GPT_ITEM_PROFILE_PROVIDER_ORDER", value = var.gpt_item_profile_provider_order },
        { name = "GPT_ITEM_PROFILE_MODEL", value = var.gpt_item_profile_model },
        { name = "GPT_ITEM_PROFILE_GEMINI_MODEL", value = var.gpt_item_profile_gemini_model },
        { name = "GPT_ITEM_PROFILE_TIMEOUT_S", value = tostring(var.gpt_item_profile_timeout_s) },
        { name = "GPT_ITEM_PROFILE_MAX_IMAGES", value = tostring(var.gpt_item_profile_max_images) },
        { name = "GPT_ITEM_PROFILE_IMAGE_DETAIL", value = var.gpt_item_profile_image_detail },
        { name = "GPT_ITEM_PROFILE_REASONING_EFFORT", value = var.gpt_item_profile_reasoning_effort },
        { name = "GPT_ITEM_PROFILE_VERTEX_SEARCH_ENABLED", value = tostring(var.gpt_item_profile_vertex_search_enabled) },
        { name = "GPT_ITEM_PROFILE_VERTEX_SEARCH_PROJECT_ID", value = var.gpt_item_profile_vertex_search_project_id },
        { name = "GPT_ITEM_PROFILE_VERTEX_SEARCH_LOCATION", value = var.gpt_item_profile_vertex_search_location },
        { name = "GPT_ITEM_PROFILE_VERTEX_SEARCH_MODEL", value = var.gpt_item_profile_vertex_search_model },
        { name = "GPT_ITEM_PROFILE_VERTEX_SEARCH_DATASTORE", value = var.gpt_item_profile_vertex_search_datastore },
        { name = "GPT_ITEM_PROFILE_VERTEX_SEARCH_ACCESS_TOKEN", value = var.gpt_item_profile_vertex_search_access_token },
        { name = "GPT_ITEM_PROFILE_VERTEX_SEARCH_MAX_RESULTS", value = tostring(var.gpt_item_profile_vertex_search_max_results) },
        { name = "FIRECRAWL_API_KEY", value = var.firecrawl_api_key },
        { name = "VALUATION_USE_FIRECRAWL", value = tostring(var.valuation_use_firecrawl) },
        { name = "VALUATION_ENABLED", value = tostring(var.valuation_enabled) },
        { name = "VALUATION_PROVIDERS", value = var.valuation_providers },
        { name = "VALUATION_MIN_COMPS", value = tostring(var.valuation_min_comps) },
        { name = "VALUATION_MAX_COMPS", value = tostring(var.valuation_max_comps) },
        { name = "VALUATION_CURRENCY", value = var.valuation_currency },
        { name = "VALUATION_PROVIDER_TIMEOUT_S", value = tostring(var.valuation_provider_timeout_s) },
        { name = "VALUATION_PROVIDER_USER_AGENT", value = var.valuation_provider_user_agent },
        { name = "EBAY_APP_ID", value = var.ebay_app_id },
        { name = "BRAND_ACCEPT_SCORE", value = tostring(var.brand_accept_score) },
        { name = "BRAND_ACCEPT_SCORE_LOW", value = tostring(var.brand_accept_score_low) },
        { name = "BRAND_GAP_MIN", value = tostring(var.brand_gap_min) }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = local.cloudwatch_log_group_name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    # Cheaper MVP option: run Fargate tasks in public subnets (ALB still fronts traffic).
    # This avoids NAT Gateway hourly cost while preserving private RDS subnets.
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]
}
