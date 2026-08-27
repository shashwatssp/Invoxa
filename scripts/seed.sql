-- Invoxa seed data
-- Insert sample vendors for development

INSERT INTO vendors (name, gstin, category) VALUES
  ('Amazon India', '27AABCCDDEEFFG', 'e-commerce'),
  ('Flipkart Private Limited', '29AAFFBBCCGGEN', 'e-commerce'),
  ('Zomato Ltd', '11AAZZZ123456', 'food-delivery'),
  ('Swiggy Technologies', '29AASSWIGGY001', 'food-delivery')
ON CONFLICT DO NOTHING;
