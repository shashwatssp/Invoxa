-- Invoxa seed data
-- Insert sample vendors for development

INSERT INTO vendors (name, gstin, category) VALUES
  ('Amazon India', '27AABCCDDEEFFZ5', 'e-commerce'),
  ('Flipkart Private Limited', '29AAFFBBCCGGEZ1', 'e-commerce'),
  ('Zomato Ltd', '11AAZZZ1234ABZ2', 'food-delivery'),
  ('Swiggy Technologies', '29AASSWIGGY00Z1', 'food-delivery')
ON CONFLICT DO NOTHING;
