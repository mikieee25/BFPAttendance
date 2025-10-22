/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.19-12.0.2-MariaDB, for Linux (x86_64)
--
-- Host: localhost    Database: bfp_sorsogon_attendance
-- ------------------------------------------------------
-- Server version	12.0.2-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*M!100616 SET @OLD_NOTE_VERBOSITY=@@NOTE_VERBOSITY, NOTE_VERBOSITY=0 */;

--
-- Table structure for table `activity_log`
--

DROP TABLE IF EXISTS `activity_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `activity_log` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `title` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `timestamp` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `user_id` (`user_id`) USING BTREE,
  CONSTRAINT `activity_log_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=76 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `attendance`
--

DROP TABLE IF EXISTS `attendance`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `attendance` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `personnel_id` int(11) NOT NULL,
  `date` date NOT NULL,
  `time_in` datetime DEFAULT NULL,
  `time_out` datetime DEFAULT NULL,
  `status` enum('PRESENT','LATE','ABSENT') DEFAULT NULL,
  `confidence_score` float DEFAULT NULL,
  `is_auto_captured` tinyint(1) DEFAULT NULL,
  `is_approved` tinyint(1) DEFAULT NULL,
  `approved_by` int(11) DEFAULT NULL,
  `time_in_image` varchar(255) DEFAULT NULL,
  `time_out_image` varchar(255) DEFAULT NULL,
  `date_created` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `approved_by` (`approved_by`) USING BTREE,
  KEY `attendance_ibfk_1` (`personnel_id`) USING BTREE,
  CONSTRAINT `attendance_ibfk_1` FOREIGN KEY (`personnel_id`) REFERENCES `personnel` (`id`) ON DELETE CASCADE,
  CONSTRAINT `attendance_ibfk_2` FOREIGN KEY (`approved_by`) REFERENCES `user` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6617 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `face_data`
--

DROP TABLE IF EXISTS `face_data`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `face_data` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `personnel_id` int(11) NOT NULL,
  `filename` varchar(255) NOT NULL,
  `embedding` longtext DEFAULT NULL,
  `confidence` float DEFAULT NULL,
  `date_created` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `personnel_id` (`personnel_id`) USING BTREE,
  CONSTRAINT `face_data_ibfk_1` FOREIGN KEY (`personnel_id`) REFERENCES `personnel` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=367 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `pending_attendance`
--

DROP TABLE IF EXISTS `pending_attendance`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `pending_attendance` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `personnel_id` int(11) NOT NULL,
  `date` date NOT NULL,
  `attendance_type` enum('TIME_IN','TIME_OUT') NOT NULL,
  `image_path` varchar(255) NOT NULL,
  `notes` text DEFAULT NULL,
  `date_created` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `personnel_id` (`personnel_id`) USING BTREE,
  CONSTRAINT `pending_attendance_ibfk_1` FOREIGN KEY (`personnel_id`) REFERENCES `personnel` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `personnel`
--

DROP TABLE IF EXISTS `personnel`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `personnel` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `first_name` varchar(100) NOT NULL,
  `last_name` varchar(100) NOT NULL,
  `rank` varchar(100) NOT NULL,
  `station_id` int(11) NOT NULL,
  `date_created` datetime DEFAULT NULL,
  `image_path` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  KEY `station_id` (`station_id`) USING BTREE,
  CONSTRAINT `personnel_ibfk_1` FOREIGN KEY (`station_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=129 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user`
--

DROP TABLE IF EXISTS `user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `user` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL,
  `email` varchar(150) NOT NULL,
  `password` varchar(255) NOT NULL,
  `station_type` enum('CENTRAL','TALISAY','BACON','ABUYOG') NOT NULL,
  `is_admin` tinyint(1) DEFAULT NULL,
  `date_created` datetime DEFAULT NULL,
  `profile_picture` varchar(255) DEFAULT 'images/profile-placeholder.jpg',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `username` (`username`) USING BTREE,
  UNIQUE KEY `email` (`email`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

-- ----------------------------
-- Records of user
-- ----------------------------
INSERT INTO `user` VALUES (1, 'admin', 'admin@bfpsorsogon.gov.ph', 'scrypt:32768:8:1$mWp6tIowDDh2chcM$fa56244f6d1db134380a505798c4825202afffb789308587a8d9b3ef41970f9644a07b2b1d159debf8c3e32721cc110d683c7e24d771e1b50d914f2fd2cefc5b', 'CENTRAL', 1, '2025-06-24 12:37:56', 'images/profile-placeholder.jpg');
INSERT INTO `user` VALUES (2, 'central', 'central@bfpsorsogon.gov.ph', 'scrypt:32768:8:1$zZRX6d1ble0Vd3zP$2d758201233b67c92cc0e6fee3a3216fb4d0c1afee11a3469451e923a936ca193bfce43ac41e0abeaeba9a24d224a757282ee24e83ee3db35f897800cb662d42', 'CENTRAL', 0, '2025-06-24 12:37:57', 'images/profile-placeholder.jpg');
INSERT INTO `user` VALUES (3, 'talisay', 'talisay@bfpsorsogon.gov.ph', 'scrypt:32768:8:1$lhZEQL87DcxDlxW9$ca10519954f745956e84862295152929b9814f46964f7a5948a257fdf6a8432ac02484653a65260c0092d5d42335f062ba9be61d0db87ae2d111cd1bfb1c8396', 'TALISAY', 0, '2025-06-24 12:37:57', 'images/profile-placeholder.jpg');
INSERT INTO `user` VALUES (4, 'bacon', 'bacon@bfpsorsogon.gov.ph', 'scrypt:32768:8:1$9vVBLAqm7sRiaWQt$3d794298ac151113c504a7a3c1edb887281ee95e5f06986bd7f424c4f4cbf083cf2affac3cc9fc420668fd5e84fee6d54345e388a1d8f20b3d5742fa68b8ebd0', 'BACON', 0, '2025-06-24 12:37:57', 'images/profile-placeholder.jpg');
INSERT INTO `user` VALUES (5, 'abuyog', 'abuyog@bfpsorsogon.gov.ph', 'scrypt:32768:8:1$boLpEhPYyPzKlNtE$8645ab2d61e15cb1c7f495bc61a48bcbea931e8583610c42def1419a4f24eb96108faeb4564d92c5961968c9f34c95be7cbed966d5f61e92f3cf0cce4369bafb', 'ABUYOG', 0, '2025-06-24 12:37:57', 'images/profile-placeholder.jpg');

SET FOREIGN_KEY_CHECKS = 1;

--
-- Dumping routines for database 'bfp_sorsogon_attendance'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*M!100616 SET NOTE_VERBOSITY=@OLD_NOTE_VERBOSITY */;

-- Dump completed on 2025-10-22 21:32:58
