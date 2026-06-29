package com.poc.pgp;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.SecureRandom;
import java.util.Date;
import java.util.Iterator;

import org.bouncycastle.openpgp.PGPCompressedData;
import org.bouncycastle.openpgp.PGPCompressedDataGenerator;
import org.bouncycastle.openpgp.PGPEncryptedData;
import org.bouncycastle.openpgp.PGPEncryptedDataGenerator;
import org.bouncycastle.openpgp.PGPEncryptedDataList;
import org.bouncycastle.openpgp.PGPLiteralData;
import org.bouncycastle.openpgp.PGPLiteralDataGenerator;
import org.bouncycastle.openpgp.PGPPrivateKey;
import org.bouncycastle.openpgp.PGPPublicKey;
import org.bouncycastle.openpgp.PGPPublicKeyEncryptedData;
import org.bouncycastle.openpgp.PGPPublicKeyRing;
import org.bouncycastle.openpgp.PGPPublicKeyRingCollection;
import org.bouncycastle.openpgp.PGPSecretKeyRingCollection;
import org.bouncycastle.openpgp.PGPUtil;
import org.bouncycastle.openpgp.jcajce.JcaPGPObjectFactory;
import org.bouncycastle.openpgp.operator.jcajce.JcaKeyFingerprintCalculator;
import org.bouncycastle.openpgp.operator.jcajce.JcePBESecretKeyDecryptorBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcePGPDataEncryptorBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcePublicKeyDataDecryptorFactoryBuilder;
import org.bouncycastle.openpgp.operator.jcajce.JcePublicKeyKeyEncryptionMethodGenerator;

public class StreamingEngine implements PgpEngine {

    private PGPPublicKey publicKey;
    private PGPSecretKeyRingCollection privateKeyCollection;

    @Override
    public String variantId() {
        return "java-stream-single";
    }

    @Override
    public void loadKeys(String keySetPath) throws Exception {
        // --- 1. โหลด Public Key ---
        File pubFile = new File(keySetPath, "rsa2048-public.asc");
        try (InputStream pubIn = new BufferedInputStream(new FileInputStream(pubFile))) {
            PGPPublicKeyRingCollection pubCollection = new PGPPublicKeyRingCollection(
                PGPUtil.getDecoderStream(pubIn), new JcaKeyFingerprintCalculator());

            // --- วนลูปหา Subkey ที่รองรับการ Encryption ---
            Iterator<PGPPublicKeyRing> rIt = pubCollection.getKeyRings();
            if (rIt.hasNext()) {
                Iterator<PGPPublicKey> kIt = rIt.next().getPublicKeys();
                while (kIt.hasNext()) {
                    PGPPublicKey k = kIt.next();
                    if (k.isEncryptionKey()) {
                        this.publicKey = k;
                        break;
                    }
                }
            }
        }

        // --- 2. โหลด Private Key ---
        File privFile = new File(keySetPath, "rsa2048-private.asc");
        try (InputStream privIn = new BufferedInputStream(new FileInputStream(privFile))) {
            this.privateKeyCollection = new PGPSecretKeyRingCollection(
                PGPUtil.getDecoderStream(privIn), new JcaKeyFingerprintCalculator());
        }
    }

    @Override
    public void encrypt(InputStream in, OutputStream out) throws Exception {
        // [Streaming] ไม่มีการสร้าง ByteArrayOutputStream

        // --- Bouncy Castle ---
        
        // ชั้นที่ 1 : AES-256 (เข้ารหัสเนื้อหา) + RSA (เข้ารหัสกุญแจ AES)
        PGPEncryptedDataGenerator encGen = new PGPEncryptedDataGenerator(
            new JcePGPDataEncryptorBuilder(PGPEncryptedData.AES_256)
                .setWithIntegrityPacket(true)
                .setSecureRandom(new SecureRandom()).setProvider("BC")
        );
        encGen.addMethod(new JcePublicKeyKeyEncryptionMethodGenerator(publicKey).setProvider("BC"));
        OutputStream encOut = encGen.open(out, new byte[4096]); // จ่ายตรงลงดิสก์

        // ชั้นที่ 2 : ZLIB บีบอัดข้อมูล
        PGPCompressedDataGenerator compGen = new PGPCompressedDataGenerator(PGPCompressedData.ZLIB);
        OutputStream compOut = compGen.open(encOut);

        // ชั้นที่ 3 : Literal Data สำหรับห่อหุ้ม Metadata (ชื่อไฟล์, วันที่)
        PGPLiteralDataGenerator litGen = new PGPLiteralDataGenerator();
        OutputStream litOut = litGen.open(
            compOut, PGPLiteralData.BINARY, "inline.txt", new Date(), new byte[4096]
        );

        // บัฟเฟอร์ขนาด 8 KB
        byte[] buffer = new byte[8192];
        int len;
        while ((len = in.read(buffer)) > 0) {
            // เขียนลงท่อชั้นในสุด แล้วดันข้อมูลออก FileOutputStream
            litOut.write(buffer, 0, len);
        }

        litOut.close();
        compGen.close();
        encGen.close();
    }

    @Override
    public void decrypt(InputStream in, OutputStream out) throws Exception {
        // เอา in (FileInputStream) เข้า Factory ไม่มีการแปลงเป็น byte[]
        InputStream decodedIn = PGPUtil.getDecoderStream(in);
        JcaPGPObjectFactory pgpFact = new JcaPGPObjectFactory(decodedIn);

        Object obj = pgpFact.nextObject();
        PGPEncryptedDataList encList = (obj instanceof PGPEncryptedDataList) 
            ? (PGPEncryptedDataList) obj : (PGPEncryptedDataList) pgpFact.nextObject();

        PGPPublicKeyEncryptedData encData = (PGPPublicKeyEncryptedData) encList.get(0);
        
        PGPPrivateKey privKey = privateKeyCollection.getSecretKey(encData.getKeyID())
            .extractPrivateKey(new JcePBESecretKeyDecryptorBuilder().setProvider("BC").build(new char[0]));

        InputStream clearStream = encData.getDataStream(
            new JcePublicKeyDataDecryptorFactoryBuilder().setProvider("BC").build(privKey)
        );

        JcaPGPObjectFactory plainFact = new JcaPGPObjectFactory(clearStream);
        Object message = plainFact.nextObject();

        if (message instanceof PGPCompressedData) {
            PGPCompressedData compData = (PGPCompressedData) message;
            plainFact = new JcaPGPObjectFactory(compData.getDataStream());
            message = plainFact.nextObject();
        }

        if (message instanceof PGPLiteralData) {
            PGPLiteralData litData = (PGPLiteralData) message;
            try (InputStream litIn = litData.getDataStream()) {
                // อ่านข้อมูลที่ถอดรหัสแล้วทีละ 8 KB แล้วเขียนลงไฟล์ปลายทางทันที
                byte[] buffer = new byte[8192];
                int length;
                while ((length = litIn.read(buffer)) > 0) {
                    out.write(buffer, 0, length);
                }
            }
        }
    }
}