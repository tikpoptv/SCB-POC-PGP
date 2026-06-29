package com.poc.pgp;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.Security;

import org.bouncycastle.jce.provider.BouncyCastleProvider;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Java PGP Runner — จุดเริ่มของโปรแกรม (CLI)
 * ---------------------------------------------------------------------------
 * โครงนี้ตั้งใจเว้นไว้ให้น้อง "เขียนเอง" เพื่อให้ได้ฝึก
 *
 * สิ่งที่ main() ต้องทำ (ออกแบบรายละเอียดเอง):
 *   1) อ่านคำสั่ง JSON จาก stdin  (ดูสัญญาใน docs/handoff-java-inmem-variant.md)
 *   2) เลือก engine ตาม variantId: "java-inmem-single" หรือ "java-stream-single"
 *   3) วนทุกไฟล์ใน corpusPath:
 *        - ถ้าเป็น .ctrl/.ctl -> ข้าม (skipped=true)
 *        - ไม่งั้น encrypt -> เขียนไฟล์ .pgp -> decrypt -> เทียบ byte-for-byte
 *        - จับเวลาเฉพาะ encrypt/decrypt (ห้ามรวม I/O และโหลดกุญแจ)
 *   4) พิมพ์ผลรวมเป็น JSON ออก stdout (log ออก stderr เท่านั้น)
 *
 * ไลบรารีที่มีให้ใน pom.xml แล้ว: Bouncy Castle (bcpg/bcprov), Jackson (JSON), JUnit
 */
public class JavaRunner {

    public static void main(String[] args) throws Exception {
        // ลงทะเบียน Provider ของ Bouncy Castle เข้าสู่สถาปัตยกรรม Security ของ Java
        Security.addProvider(new BouncyCastleProvider());

        // --- ส่วนที่ 1: การจัดการ I/O (Input) ---
        ObjectMapper mapper = new ObjectMapper();
        ObjectNode inputJson;
        try {
            // อ่าน JSON ทั้งก้อนจาก Standard Input (stdin)
            inputJson = (ObjectNode) mapper.readTree(System.in);
        } catch (Exception e) {
            System.err.println("Error: Cannot parse input JSON from stdin.");
            System.exit(1);
            return;
        }

        // ดึงค่า Configuration ต่าง ๆ ที่ Harness ส่งมาให้
        String command = inputJson.get("command").asText();
        String variantId = inputJson.get("variantId").asText();
        String keySetPath = inputJson.get("keySetPath").asText();
        String corpusPath = inputJson.get("corpusPath").asText();
        String outputDirStr = inputJson.get("outputDir").asText();

        if (!"run".equals(command)) {
            System.err.println("Error: Unsupported command " + command);
            System.exit(1);
        }

        // --- ส่วนที่ 2: สร้างและเตรียม Engine ---
        PgpEngine engine;
        if ("java-inmem-single".equals(variantId)) {
            engine = new InMemoryEngine();
        } else if ("java-stream-single".equals(variantId)) {
            engine = new StreamingEngine();
        } else {
            System.err.println("Error: Unknown variantId -> " + variantId);
            System.exit(1);
            return;
        }

        // โหลดกุญแจขึ้น RAM ก่อนเริ่มกระบวนการจับเวลา
        System.err.println("[" + variantId + "] Loading keys...");
        engine.loadKeys(keySetPath);

        File outputDir = new File(outputDirStr);
        if (!outputDir.exists()) outputDir.mkdirs();

        // --- ส่วนที่ 3: เตรียมโครงสร้าง JSON Output ---
        ObjectNode outputJson = mapper.createObjectNode();
        outputJson.put("runnerId", "java");
        outputJson.put("variantId", variantId);
        ArrayNode operationsArray = mapper.createArrayNode();

        // --- ส่วนที่ 4: วนลูปประมวลผลไฟล์ ---
        File corpusFolder = new File(corpusPath);
        File[] files = corpusFolder.listFiles();

        if (files != null) {
            for (File file : files) {
                if (!file.isFile()) continue;

                String fileName = file.getName();
                ObjectNode opResult = mapper.createObjectNode();
                opResult.put("fileName", fileName);
                opResult.put("originalBytes", file.length());

                // ดัก Edge Case: ถ้าเจอนามสกุลไฟล์ควบคุม ให้ข้ามทันที
                if (fileName.endsWith(".ctrl") || fileName.endsWith(".ctl")) {
                    System.err.println("Skipping control file: " + fileName);
                    opResult.put("ciphertextBytes", 0);
                    opResult.put("encryptMs", 0.0);
                    opResult.put("decryptMs", 0.0);
                    opResult.put("roundTripOk", false);
                    opResult.put("skipped", true);
                    opResult.put("outputFileName", "");
                    operationsArray.add(opResult);
                    continue;
                }

                System.err.println("Processing: " + fileName);
                
                File encryptedFile = new File(outputDir, fileName + ".pgp");
                File decryptedFile = new File(outputDir, fileName + ".decrypted");

                double encryptMs = 0;
                double decryptMs = 0;
                boolean roundTripOk = false;

                try {
                    // [การจับเวลา] ใช้ try-with-resources เปิด Stream ทิ้งไว้ล่วงหน้า
                    // เพื่อให้เวลา Disk I/O ตอนเปิดไฟล์ ไม่เข้ามารบกวนเวลาทำ Crypto
                    try (InputStream in = new BufferedInputStream(new FileInputStream(file));
                         OutputStream out = new BufferedOutputStream(new FileOutputStream(encryptedFile))) {
                        
                        long startTime = System.nanoTime();
                        engine.encrypt(in, out); // <--- วัดผลการ Encrypt ที่บรรทัดนี้
                        long endTime = System.nanoTime();
                        
                        // หารด้วย 1 ล้านเพื่อแปลง Nano เป็น Milli
                        encryptMs = (endTime - startTime) / 1_000_000.0; 
                    }

                    try (InputStream in = new BufferedInputStream(new FileInputStream(encryptedFile));
                         OutputStream out = new BufferedOutputStream(new FileOutputStream(decryptedFile))) {
                        
                        long startTime = System.nanoTime();
                        engine.decrypt(in, out); // <--- วัดผลการ Decrypt ที่บรรทัดนี้
                        long endTime = System.nanoTime();
                        
                        decryptMs = (endTime - startTime) / 1_000_000.0;
                    }

                    // พิสูจน์ความถูกต้อง
                    roundTripOk = checkRoundTrip(file, decryptedFile);

                } catch (Exception ex) {
                    System.err.println("Error on " + fileName + ": " + ex.getMessage());
                } finally {
                    if (decryptedFile.exists()) decryptedFile.delete(); // ล้างไฟล์ขยะ
                }

                // บันทึกผลลัพธ์รายไฟล์
                opResult.put("ciphertextBytes", encryptedFile.exists() ? encryptedFile.length() : 0);
                opResult.put("encryptMs", encryptMs);
                opResult.put("decryptMs", decryptMs);
                opResult.put("roundTripOk", roundTripOk);
                opResult.put("skipped", false);
                opResult.put("outputFileName", fileName + ".pgp");
                operationsArray.add(opResult);
            }
        }

        outputJson.set("operations", operationsArray);

        // --- ส่วนที่ 5: พิมพ์ผลลัพธ์ออก stdout ---
        System.out.print(mapper.writeValueAsString(outputJson));
        System.out.flush();
    }

    // ฟังก์ชันตรวจสอบความถูกต้องของไฟล์แบบ Byte-for-Byte
    private static boolean checkRoundTrip(File original, File decrypted) throws IOException {
        if (original.length() != decrypted.length()) return false;
        
        try (InputStream in1 = new BufferedInputStream(new FileInputStream(original));
             InputStream in2 = new BufferedInputStream(new FileInputStream(decrypted))) {
            int b1;
            while ((b1 = in1.read()) != -1) {
                if (b1 != in2.read()) return false;
            }
            return true;
        }
    }
}
