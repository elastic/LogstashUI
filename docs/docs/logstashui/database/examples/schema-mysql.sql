-- Snapshot of LogstashUI 0.5.2 `migrate` DDL on MySQL 8.0 (utf8mb4_bin).
-- Generated with mysqldump --no-data. Do NOT apply this instead of
-- `logstashui manage migrate --noinput`. It will go stale with new migrations.
-- Create the empty database first (see create-mysql.sql / create-mariadb.sql).


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
DROP TABLE IF EXISTS `Management_userprofile`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Management_userprofile` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `role` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  `user_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`),
  CONSTRAINT `Management_userprofile_user_id_70f1a900_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `PipelineManager_apikey`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `PipelineManager_apikey` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `api_key` varchar(512) COLLATE utf8mb4_bin NOT NULL,
  `connection_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `PipelineManager_apik_connection_id_27156847_fk_PipelineM` (`connection_id`),
  CONSTRAINT `PipelineManager_apik_connection_id_27156847_fk_PipelineM` FOREIGN KEY (`connection_id`) REFERENCES `PipelineManager_connection` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `PipelineManager_connection`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `PipelineManager_connection` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `connection_type` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  `host` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  `port` int unsigned DEFAULT NULL,
  `username` varchar(100) COLLATE utf8mb4_bin DEFAULT NULL,
  `password` varchar(512) COLLATE utf8mb4_bin DEFAULT NULL,
  `ssh_key` longtext COLLATE utf8mb4_bin,
  `cloud_id` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  `cloud_url` varchar(200) COLLATE utf8mb4_bin DEFAULT NULL,
  `api_key` varchar(512) COLLATE utf8mb4_bin DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `policy_id` bigint DEFAULT NULL,
  `agent_id` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  `last_check_in` datetime(6) DEFAULT NULL,
  `status_blob` json DEFAULT NULL,
  `restart_on_next_checkin` tinyint(1) NOT NULL,
  `desired_agent_version` varchar(20) COLLATE utf8mb4_bin DEFAULT NULL,
  `agent_api_port` int unsigned DEFAULT NULL,
  `instance_id` int unsigned DEFAULT NULL,
  `last_selected_at` datetime(6) DEFAULT NULL,
  `logstash_api_port` int unsigned DEFAULT NULL,
  `logstash_version_resolved` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `agent_id` (`agent_id`),
  KEY `PipelineManager_conn_policy_id_819d316d_fk_PipelineM` (`policy_id`),
  CONSTRAINT `PipelineManager_conn_policy_id_819d316d_fk_PipelineM` FOREIGN KEY (`policy_id`) REFERENCES `PipelineManager_policy` (`id`),
  CONSTRAINT `PipelineManager_connection_chk_1` CHECK ((`port` >= 0)),
  CONSTRAINT `PipelineManager_connection_chk_2` CHECK ((`agent_api_port` >= 0)),
  CONSTRAINT `PipelineManager_connection_chk_3` CHECK ((`instance_id` >= 0)),
  CONSTRAINT `PipelineManager_connection_chk_4` CHECK ((`logstash_api_port` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `PipelineManager_enrollmenttoken`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `PipelineManager_enrollmenttoken` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `token` varchar(512) COLLATE utf8mb4_bin NOT NULL,
  `policy_id` bigint NOT NULL,
  `name` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_token_name_per_policy` (`policy_id`,`name`),
  CONSTRAINT `PipelineManager_enro_policy_id_355d6dca_fk_PipelineM` FOREIGN KEY (`policy_id`) REFERENCES `PipelineManager_policy` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `PipelineManager_keystore`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `PipelineManager_keystore` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `key_name` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `key_value` varchar(512) COLLATE utf8mb4_bin NOT NULL,
  `last_updated` datetime(6) NOT NULL,
  `policy_id` bigint NOT NULL,
  `revision_number` int NOT NULL,
  `kv_hash` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `managed_by` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_key_per_policy` (`policy_id`,`key_name`),
  CONSTRAINT `PipelineManager_keys_policy_id_6309b699_fk_PipelineM` FOREIGN KEY (`policy_id`) REFERENCES `PipelineManager_policy` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `PipelineManager_pipeline`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `PipelineManager_pipeline` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `description` longtext COLLATE utf8mb4_bin,
  `lscl` longtext COLLATE utf8mb4_bin NOT NULL,
  `lscl_hash` varchar(64) COLLATE utf8mb4_bin DEFAULT NULL,
  `last_updated` datetime(6) NOT NULL,
  `policy_id` bigint NOT NULL,
  `revision_number` int NOT NULL,
  `pipeline_batch_delay` int NOT NULL,
  `pipeline_batch_size` int NOT NULL,
  `pipeline_workers` int NOT NULL,
  `queue_checkpoint_writes` int NOT NULL,
  `queue_max_bytes` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  `queue_type` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  `pipeline_hash` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `no_input` tinyint(1) NOT NULL,
  `non_reloadable` tinyint(1) NOT NULL,
  `managed_by` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_pipeline_per_policy` (`policy_id`,`name`),
  CONSTRAINT `PipelineManager_pipe_policy_id_7c3a6fd9_fk_PipelineM` FOREIGN KEY (`policy_id`) REFERENCES `PipelineManager_policy` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `PipelineManager_policy`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `PipelineManager_policy` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `settings_path` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `logs_path` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `logstash_yml` longtext COLLATE utf8mb4_bin NOT NULL,
  `jvm_options` longtext COLLATE utf8mb4_bin NOT NULL,
  `log4j2_properties` longtext COLLATE utf8mb4_bin NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `current_revision_number` int NOT NULL,
  `has_undeployed_changes` tinyint(1) NOT NULL,
  `jvm_options_hash` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `log4j2_properties_hash` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `logstash_yml_hash` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `binary_path` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `keystore_password` varchar(512) COLLATE utf8mb4_bin DEFAULT NULL,
  `keystore_password_hash` varchar(64) COLLATE utf8mb4_bin NOT NULL,
  `last_deployed_at` datetime(6) DEFAULT NULL,
  `agent_api_port` int unsigned NOT NULL,
  `cloned_from_id` bigint DEFAULT NULL,
  `data_path` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `is_system` tinyint(1) NOT NULL,
  `keystore_env_file` varchar(512) COLLATE utf8mb4_bin NOT NULL,
  `logstash_api_port` int unsigned NOT NULL,
  `logstash_download_dir` varchar(512) COLLATE utf8mb4_bin NOT NULL,
  `logstash_source` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  `logstash_version` varchar(32) COLLATE utf8mb4_bin NOT NULL,
  `policy_type` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `PipelineManager_poli_cloned_from_id_4177e74a_fk_PipelineM` (`cloned_from_id`),
  CONSTRAINT `PipelineManager_poli_cloned_from_id_4177e74a_fk_PipelineM` FOREIGN KEY (`cloned_from_id`) REFERENCES `PipelineManager_policy` (`id`),
  CONSTRAINT `PipelineManager_policy_chk_1` CHECK ((`agent_api_port` >= 0)),
  CONSTRAINT `PipelineManager_policy_chk_2` CHECK ((`logstash_api_port` >= 0))
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `PipelineManager_revision`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `PipelineManager_revision` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `revision_number` int NOT NULL,
  `snapshot_json` json NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `created_by` varchar(150) COLLATE utf8mb4_bin NOT NULL,
  `policy_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_revision_per_policy` (`policy_id`,`revision_number`),
  CONSTRAINT `PipelineManager_revi_policy_id_99e7d146_fk_PipelineM` FOREIGN KEY (`policy_id`) REFERENCES `PipelineManager_policy` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `SNMP_credential`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `SNMP_credential` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `description` longtext COLLATE utf8mb4_bin NOT NULL,
  `version` varchar(2) COLLATE utf8mb4_bin NOT NULL,
  `community` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `security_name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `security_level` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  `auth_protocol` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  `auth_pass` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `priv_protocol` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  `priv_pass` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `SNMP_device`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `SNMP_device` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `ip_address` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  `port` int NOT NULL,
  `retries` int NOT NULL,
  `timeout` int NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `credential_id` bigint DEFAULT NULL,
  `network_id` bigint DEFAULT NULL,
  `device_template_id` bigint DEFAULT NULL,
  `hostname` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  `building` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  `latitude` decimal(15,10) DEFAULT NULL,
  `longitude` decimal(15,10) DEFAULT NULL,
  `metadata` json NOT NULL DEFAULT (_utf8mb4'{}'),
  `room` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  `site` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `SNMP_device_credential_id_f229ff4e_fk_SNMP_credential_id` (`credential_id`),
  KEY `SNMP_device_name_087021_idx` (`name`),
  KEY `SNMP_device_ip_addr_6a90e5_idx` (`ip_address`),
  KEY `SNMP_device_created_becb56_idx` (`created_at` DESC),
  KEY `SNMP_device_network_889f1c_idx` (`network_id`,`name`),
  KEY `SNMP_device_device_template_id_ca143332_fk_SNMP_devi` (`device_template_id`),
  KEY `SNMP_device_hostnam_fae88a_idx` (`hostname`),
  CONSTRAINT `SNMP_device_credential_id_f229ff4e_fk_SNMP_credential_id` FOREIGN KEY (`credential_id`) REFERENCES `SNMP_credential` (`id`),
  CONSTRAINT `SNMP_device_device_template_id_ca143332_fk_SNMP_devi` FOREIGN KEY (`device_template_id`) REFERENCES `SNMP_devicetemplate` (`id`),
  CONSTRAINT `SNMP_device_network_id_4dea94fa_fk_SNMP_network_id` FOREIGN KEY (`network_id`) REFERENCES `SNMP_network` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `SNMP_devicetemplate`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `SNMP_devicetemplate` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `description` longtext COLLATE utf8mb4_bin NOT NULL,
  `vendor` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `model` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `matching_rules` json NOT NULL,
  `official` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `product` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `type` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `official_key` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  UNIQUE KEY `official_key` (`official_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `SNMP_devicetemplate_profiles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `SNMP_devicetemplate_profiles` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `devicetemplate_id` bigint NOT NULL,
  `profile_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `SNMP_devicetemplate_prof_devicetemplate_id_profil_fb6396a5_uniq` (`devicetemplate_id`,`profile_id`),
  KEY `SNMP_devicetemplate__profile_id_4cb23513_fk_SNMP_prof` (`profile_id`),
  CONSTRAINT `SNMP_devicetemplate__devicetemplate_id_da70425d_fk_SNMP_devi` FOREIGN KEY (`devicetemplate_id`) REFERENCES `SNMP_devicetemplate` (`id`),
  CONSTRAINT `SNMP_devicetemplate__profile_id_4cb23513_fk_SNMP_prof` FOREIGN KEY (`profile_id`) REFERENCES `SNMP_profile` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `SNMP_network`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `SNMP_network` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `network_range` varchar(50) COLLATE utf8mb4_bin NOT NULL,
  `discovery_enabled` tinyint(1) NOT NULL,
  `traps_enabled` tinyint(1) NOT NULL,
  `interval` int unsigned NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `connection_id` bigint DEFAULT NULL,
  `credential_id` bigint DEFAULT NULL,
  `discovery_credential_id` bigint DEFAULT NULL,
  `namespace` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `namespace_from_device_template` tinyint(1) NOT NULL,
  `agent_connection_id` bigint DEFAULT NULL,
  `deployment_mode` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  `credential_mode` varchar(20) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `SNMP_network_connection_id_432a2f88_fk_PipelineM` (`connection_id`),
  KEY `SNMP_network_credential_id_3b15dfc1_fk_SNMP_credential_id` (`credential_id`),
  KEY `SNMP_network_discovery_credential_d9229589_fk_SNMP_cred` (`discovery_credential_id`),
  KEY `SNMP_network_agent_connection_id_cf646bb5_fk_PipelineM` (`agent_connection_id`),
  CONSTRAINT `SNMP_network_agent_connection_id_cf646bb5_fk_PipelineM` FOREIGN KEY (`agent_connection_id`) REFERENCES `PipelineManager_connection` (`id`),
  CONSTRAINT `SNMP_network_connection_id_432a2f88_fk_PipelineM` FOREIGN KEY (`connection_id`) REFERENCES `PipelineManager_connection` (`id`),
  CONSTRAINT `SNMP_network_credential_id_3b15dfc1_fk_SNMP_credential_id` FOREIGN KEY (`credential_id`) REFERENCES `SNMP_credential` (`id`),
  CONSTRAINT `SNMP_network_discovery_credential_d9229589_fk_SNMP_cred` FOREIGN KEY (`discovery_credential_id`) REFERENCES `SNMP_credential` (`id`),
  CONSTRAINT `SNMP_network_chk_1` CHECK ((`interval` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `SNMP_profile`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `SNMP_profile` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `profile_data` json NOT NULL,
  `description` longtext COLLATE utf8mb4_bin NOT NULL,
  `vendor` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `product` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `normalizers` json NOT NULL DEFAULT (_utf8mb4'[]'),
  `official_key` varchar(255) COLLATE utf8mb4_bin DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  UNIQUE KEY `official_key` (`official_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `auth_group`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_group` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(150) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `auth_group_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_group_permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` (`group_id`,`permission_id`),
  KEY `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` (`permission_id`),
  CONSTRAINT `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  CONSTRAINT `auth_group_permissions_group_id_b120cbf9_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `auth_permission`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_permission` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `content_type_id` int NOT NULL,
  `codename` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_permission_content_type_id_codename_01ab375a_uniq` (`content_type_id`,`codename`),
  CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=85 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `auth_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_user` (
  `id` int NOT NULL AUTO_INCREMENT,
  `password` varchar(128) COLLATE utf8mb4_bin NOT NULL,
  `last_login` datetime(6) DEFAULT NULL,
  `is_superuser` tinyint(1) NOT NULL,
  `username` varchar(150) COLLATE utf8mb4_bin NOT NULL,
  `first_name` varchar(150) COLLATE utf8mb4_bin NOT NULL,
  `last_name` varchar(150) COLLATE utf8mb4_bin NOT NULL,
  `email` varchar(254) COLLATE utf8mb4_bin NOT NULL,
  `is_staff` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `date_joined` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `auth_user_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_user_groups` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `group_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_groups_user_id_group_id_94350c0c_uniq` (`user_id`,`group_id`),
  KEY `auth_user_groups_group_id_97559544_fk_auth_group_id` (`group_id`),
  CONSTRAINT `auth_user_groups_group_id_97559544_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`),
  CONSTRAINT `auth_user_groups_user_id_6a12ed8b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `auth_user_user_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_user_user_permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_user_permissions_user_id_permission_id_14a6b632_uniq` (`user_id`,`permission_id`),
  KEY `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` (`permission_id`),
  CONSTRAINT `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  CONSTRAINT `auth_user_user_permissions_user_id_a95ead1b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `django_admin_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_admin_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `action_time` datetime(6) NOT NULL,
  `object_id` longtext COLLATE utf8mb4_bin,
  `object_repr` varchar(200) COLLATE utf8mb4_bin NOT NULL,
  `action_flag` smallint unsigned NOT NULL,
  `change_message` longtext COLLATE utf8mb4_bin NOT NULL,
  `content_type_id` int DEFAULT NULL,
  `user_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `django_admin_log_content_type_id_c4bce8eb_fk_django_co` (`content_type_id`),
  KEY `django_admin_log_user_id_c564eba6_fk_auth_user_id` (`user_id`),
  CONSTRAINT `django_admin_log_content_type_id_c4bce8eb_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`),
  CONSTRAINT `django_admin_log_user_id_c564eba6_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`),
  CONSTRAINT `django_admin_log_chk_1` CHECK ((`action_flag` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `django_content_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_content_type` (
  `id` int NOT NULL AUTO_INCREMENT,
  `app_label` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  `model` varchar(100) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`)
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `django_migrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_migrations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `app` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `applied` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=76 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `django_session`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_session` (
  `session_key` varchar(40) COLLATE utf8mb4_bin NOT NULL,
  `session_data` longtext COLLATE utf8mb4_bin NOT NULL,
  `expire_date` datetime(6) NOT NULL,
  PRIMARY KEY (`session_key`),
  KEY `django_session_expire_date_a5c62663` (`expire_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `settings` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `experimental_mode` tinyint(1) NOT NULL,
  `agent_ui_url` varchar(512) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `snmp_deployment_state`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `snmp_deployment_state` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `last_deployment` datetime(6) DEFAULT NULL,
  `last_config_change` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

